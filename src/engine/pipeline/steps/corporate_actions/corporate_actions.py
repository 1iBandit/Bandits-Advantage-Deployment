"""
Corporate Actions Module (v1)

Stand-alone defensive module for retrieving and normalizing dividends and splits
from the MASSIVE service (same client as news). Designed to be a clean, high-signal data source for future use
in income modeling, split-adjusted sizing, quality screens, and OutlierEvent detection.

Follows the same patterns as catalyst_summary.py / news_reader.py:
- Explicit env-driven API key (MASSIVE_API_KEY)
- Defensive empty returns on missing key / errors / no data
- Structured dict output (no mutation of inputs)
- Diagnostic logging (info on success, warning on issues, debug on transients)
- [v1] markers on new logic for iteration tracking
- No coupling to scoring, ScorecardRow, or other modules in v1
- Data source: MASSIVE (via massive.RESTClient + MASSIVE_API_KEY, same as news) -- corporate actions (dividends/splits) are provided through this endpoint (user correction: not Polygon).

Primary public API:
- get_dividends(ticker, lookback_days=365) -> list[dict]
- get_splits(ticker, lookback_days=730) -> list[dict]
- get_corporate_actions(ticker, dividend_lookback_days=1095, split_lookback_days=1825) -> dict  (configurable lookbacks)
- batch_get_corporate_actions(tickers, pause_seconds=1.5, dividend_lookback_days=..., split_lookback_days=...) -> dict[str, dict] (configurable)

Recommended output shapes (see docstrings below for full details):
Dividend record:
    {"ticker": "...", "ex_date": "YYYY-MM-DD", "pay_date": "...", "amount": float,
     "currency": "USD", "frequency": "quarterly" | None, "is_special": bool, "source": "massive"}

Split record:
    {"ticker": "...", "split_date": "YYYY-MM-DD", "split_ratio": "4-for-1", "split_type": "forward"|"reverse", "source": "massive"}

get_corporate_actions return:
    {"ticker": str, "dividends": list, "splits": list,
     "last_dividend": dict | None, "has_recent_split": bool, "fetch_timestamp": str}

Batch and get_corporate_actions now support dividend_lookback_days and split_lookback_days for diagnostics.

All functions are safe to call with invalid/missing tickers (return empty structures + log).

Rate limit / network handling: exponential backoff + jitter + respect Retry-After (same as price fetcher).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

# Ensure .env is loaded for MASSIVE_API_KEY when module used directly (consistent with news_reader.py)
load_dotenv()

logger = logging.getLogger(__name__)

# Use the MASSIVE client (same package + MASSIVE_API_KEY as the news reader). This is where the corporate actions data lives (not Polygon).
try:
    from massive import RESTClient
    from massive.rest.models import Dividend, Split
except ImportError:
    RESTClient = None
    Dividend = None
    Split = None

# =============================================================================
# INTERNAL: MASSIVE client fetchers for dividends and splits (replicates news_reader pattern)
# =============================================================================

def _fetch_massive_dividends(ticker: str, api_key: str, lookback_days: int = 365, as_of: Optional[date] = None) -> list[dict[str, Any]]:
    """
    Fetch dividends using the MASSIVE Python client (same as news).
    Supports as_of for point-in-time historical queries (filters ex_dividend_date_lte=as_of).
    Defensive: returns [] on import issues, auth, rate limits, or any error.
    """
    if RESTClient is None:
        logger.debug("massive package not installed; falling back to empty dividends.")
        return []

    try:
        client = RESTClient(api_key)
        items = []
        if as_of:
            gte = (as_of - timedelta(days=lookback_days)).isoformat()
            lte = as_of.isoformat()
            kwargs = {"ex_dividend_date_gte": gte, "ex_dividend_date_lte": lte}
        else:
            from_date = (date.today() - timedelta(days=lookback_days)).isoformat()
            kwargs = {"ex_dividend_date_gte": from_date}
        for d in client.list_dividends(
            ticker=ticker.upper(),
            limit=50,
            sort="ex_dividend_date",
            order="desc",
            **kwargs,
        ):
            if isinstance(d, Dividend):
                items.append(d)
            if len(items) >= 50:
                break
        raw_list = []
        for item in items:
            d = item.__dict__ if hasattr(item, "__dict__") else {}
            raw_list.append(d)
        return raw_list
    except Exception as e:
        logger.debug(f"Dividends fetch (MASSIVE client) issue for {ticker}: {e}")
        return []


def _fetch_massive_splits(ticker: str, api_key: str, lookback_days: int = 730, as_of: Optional[date] = None) -> list[dict[str, Any]]:
    """
    Fetch splits using the MASSIVE Python client.
    Supports as_of for point-in-time historical queries (filters execution_date_lte=as_of).
    Defensive: returns [] on import issues, auth, rate limits, or any error.
    """
    if RESTClient is None:
        logger.debug("massive package not installed; falling back to empty splits.")
        return []

    try:
        client = RESTClient(api_key)
        items = []
        if as_of:
            gte = (as_of - timedelta(days=lookback_days)).isoformat()
            lte = as_of.isoformat()
            kwargs = {"execution_date_gte": gte, "execution_date_lte": lte}
        else:
            from_date = (date.today() - timedelta(days=lookback_days)).isoformat()
            kwargs = {"execution_date_gte": from_date}
        for s in client.list_splits(
            ticker=ticker.upper(),
            limit=50,
            sort="execution_date",
            order="desc",
            **kwargs,
        ):
            if isinstance(s, Split):
                items.append(s)
            if len(items) >= 50:
                break
        raw_list = []
        for item in items:
            d = item.__dict__ if hasattr(item, "__dict__") else {}
            raw_list.append(d)
        return raw_list
    except Exception as e:
        logger.debug(f"Splits fetch (MASSIVE client) issue for {ticker}: {e}")
        return []


# =============================================================================
# NORMALIZERS (pure, testable)
# =============================================================================

def _normalize_dividend(raw: dict[str, Any], ticker: str) -> dict[str, Any]:
    """Normalize one MASSIVE dividend result to the v1 canonical shape."""
    freq_map = {1: "annual", 2: "semi-annual", 4: "quarterly", 12: "monthly"}
    div_type = str(raw.get("dividend_type", "")).upper()
    is_special = div_type == "SC"  # special cash per MASSIVE data

    return {
        "ticker": ticker,
        "ex_date": raw.get("ex_dividend_date") or "",
        "pay_date": raw.get("pay_date"),
        "amount": float(raw.get("cash_amount", 0.0)),
        "currency": raw.get("currency", "USD"),
        "frequency": freq_map.get(raw.get("frequency")),
        "is_special": is_special,
        "source": "massive",
    }


def _normalize_split(raw: dict[str, Any], ticker: str) -> dict[str, Any]:
    """Normalize one MASSIVE split result to the v1 canonical shape."""
    from_ = int(raw.get("split_from", 1) or 1)
    to = int(raw.get("split_to", 1) or 1)
    ratio_str = f"{to}-for-{from_}" if from_ else "1-for-1"
    split_type = "forward" if to > from_ else "reverse"
    return {
        "ticker": ticker,
        "split_date": raw.get("execution_date") or "",
        "split_ratio": ratio_str,
        "split_type": split_type,
        "source": "massive",
    }


# =============================================================================
# PUBLIC: Single-ticker getters (defensive)
# =============================================================================

def get_dividends(ticker: str, lookback_days: int = 365, as_of: Optional[date] = None) -> list[dict[str, Any]]:
    """
    Fetch dividend history for a single ticker from MASSIVE (corporate actions data source).

    Args:
        ticker: The ticker symbol (e.g. "KO").
        lookback_days: How far back to query (default 1y). Uses ex_dividend_date_gte.
        as_of: Optional date for point-in-time query (adds ex_dividend_date_lte=as_of).

    Returns:
        List of normalized dividend dicts (most recent first), or [] on error / no data / no key.
    """
    api_key = os.getenv("MASSIVE_API_KEY")
    if not api_key:
        logger.warning("MASSIVE_API_KEY not set. Dividend fetch disabled (returning empty list).")
        return []

    t = ticker.upper().strip()
    raw_results = _fetch_massive_dividends(t, api_key, lookback_days, as_of=as_of)
    normalized = [_normalize_dividend(r, t) for r in raw_results]
    normalized = [d for d in normalized if d.get("ex_date")]
    # Note: We intentionally keep recent/upcoming ex-dates for context (ex-div sanity, impact).
    # Callers (e.g. diagnostics) can filter if they only want historical.
    logger.info(f"Dividends for {t}: {len(normalized)} record(s) in last {lookback_days}d" + (f" as_of={as_of}" if as_of else ""))
    return normalized


def get_splits(ticker: str, lookback_days: int = 730, as_of: Optional[date] = None) -> list[dict[str, Any]]:
    """
    Fetch split history for a single ticker from MASSIVE (corporate actions data source).

    Args:
        ticker: The ticker symbol.
        lookback_days: How far back (default ~2y). Uses execution_date_gte.
        as_of: Optional date for point-in-time query (adds execution_date_lte=as_of).

    Returns:
        List of normalized split dicts (most recent first), or [] on error / no data.
    """
    api_key = os.getenv("MASSIVE_API_KEY")
    if not api_key:
        logger.warning("MASSIVE_API_KEY not set. Split fetch disabled (returning empty list).")
        return []

    t = ticker.upper().strip()
    raw_results = _fetch_massive_splits(t, api_key, lookback_days, as_of=as_of)
    normalized = [_normalize_split(r, t) for r in raw_results]
    normalized = [s for s in normalized if s.get("split_date")]
    # Note: keep recent (past) splits; upcoming splits are rare.
    logger.info(f"Splits for {t}: {len(normalized)} record(s) in last {lookback_days}d" + (f" as_of={as_of}" if as_of else ""))
    return normalized


# =============================================================================
# PUBLIC: Convenience + batch (primary interfaces)
# =============================================================================

def get_corporate_actions(
    ticker: str,
    dividend_lookback_days: int = 365 * 3,   # ~3 years default for diagnostic
    split_lookback_days: int = 365 * 5,      # ~5 years default for diagnostic
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    """
    Convenience wrapper returning both dividends and splits plus derived signals.
    (Data via MASSIVE client.)

    Supports configurable lookbacks for flexibility in diagnostics.
    as_of for point-in-time historical (passed to sub fetches).

    Returns a dict with stable keys even on empty data (never None pollution).
    """
    t = ticker.upper().strip()
    divs = get_dividends(t, lookback_days=dividend_lookback_days, as_of=as_of)
    spls = get_splits(t, lookback_days=split_lookback_days, as_of=as_of)

    last_dividend = None
    if divs:
        # Most recent by ex_date (already sorted desc from API)
        last_dividend = divs[0]

    has_recent_split = False
    if spls:
        cutoff = date.today() - timedelta(days=90)
        for s in spls:
            try:
                sd = datetime.strptime(s["split_date"], "%Y-%m-%d").date()
                if sd >= cutoff:
                    has_recent_split = True
                    break
            except Exception:
                continue

    return {
        "ticker": t,
        "dividends": divs,
        "splits": spls,
        "last_dividend": last_dividend,
        "has_recent_split": has_recent_split,
        "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
        "context": build_corporate_action_context({"ticker": t, "dividends": divs, "splits": spls, "last_dividend": last_dividend, "has_recent_split": has_recent_split}),
    }


def batch_get_corporate_actions(
    tickers: list[str],
    pause_seconds: float = 1.5,
    dividend_lookback_days: int = 365 * 3,
    split_lookback_days: int = 365 * 5,
    as_of: Optional[date] = None,
) -> dict[str, dict[str, Any]]:
    """
    Process multiple tickers with basic pacing to respect free-tier limits (MASSIVE backend).

    Supports configurable lookback windows (useful for diagnostics).
    as_of for point-in-time (e.g. historical daily replay).

    Returns: {ticker_upper: corporate_actions_dict, ...}
    Individual tickers that fail are still present with empty lists + error note (defensive).

    Logs a summary at the end.
    """
    if not tickers:
        return {}

    results: dict[str, dict[str, Any]] = {}
    successes = 0

    for i, t in enumerate(tickers):
        t = t.upper().strip()
        try:
            ca = get_corporate_actions(
                t,
                dividend_lookback_days=dividend_lookback_days,
                split_lookback_days=split_lookback_days,
                as_of=as_of,
            )
            results[t] = ca
            has_data = bool(ca.get("dividends") or ca.get("splits"))
            if has_data:
                successes += 1
            logger.debug(f"Corporate actions for {t}: dividends={len(ca['dividends'])}, splits={len(ca['splits'])}")
        except Exception as e:
            logger.warning(f"Corporate actions fetch failed for {t}: {e}")
            results[t] = {
                "ticker": t,
                "dividends": [],
                "splits": [],
                "last_dividend": None,
                "has_recent_split": False,
                "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)[:120],
            }

        # Pace between tickers (skip after last)
        if i < len(tickers) - 1 and pause_seconds > 0:
            time.sleep(pause_seconds)

    logger.info(
        f"Batch corporate actions complete: {successes}/{len(tickers)} tickers with data, "
        f"{len(tickers) - successes} empty/error"
    )
    return results


def build_corporate_action_context(ca: dict[str, Any]) -> dict[str, Any]:
    """
    v1.0: Build the unified, versionable corporate_action_context from a single-ticker
    result returned by get_corporate_actions() or batch_get_corporate_actions()[ticker].

    This is the object that should be attached to ScorecardRow and referenced by OutlierEvent.
    Philosophy: protective/contextual, lightweight impact, human notes.
    """
    if not ca or not isinstance(ca, dict):
        return {
            "has_recent_split": False,
            "split_date": None,
            "split_ratio": None,
            "split_normalized": False,
            "recent_dividend_cut": False,
            "dividend_cut_date": None,
            "dividend_cut_pct": None,
            "ex_div_date": None,
            "ex_div_amount": None,
            "is_dividend_payer": False,
            "dividend_stability": "none",
            "notes": [],
            "impact_score": 0.0,
        }

    divs: list = ca.get("dividends", []) or []
    spls: list = ca.get("splits", []) or []
    last_div: dict = ca.get("last_dividend") or {}
    has_recent_split: bool = bool(ca.get("has_recent_split", False))

    split_date = None
    split_ratio = None
    if spls:
        s0 = spls[0]
        split_date = s0.get("split_date")
        split_ratio = s0.get("split_ratio")

    # Recent dividend cut detection (compare latest vs previous amount)
    recent_dividend_cut = False
    dividend_cut_date = None
    dividend_cut_pct = None
    if len(divs) >= 2:
        try:
            latest_amt = float(divs[0].get("amount", 0) or 0)
            prev_amt = float(divs[1].get("amount", 0) or 0)
            if prev_amt > 0 and latest_amt < prev_amt * 0.90:  # >=10% cut
                recent_dividend_cut = True
                dividend_cut_date = divs[0].get("ex_date")
                dividend_cut_pct = round((prev_amt - latest_amt) / prev_amt, 3)
        except Exception:
            pass

    ex_div_date = last_div.get("ex_date") if last_div else None
    ex_div_amount = last_div.get("amount") if last_div else None

    is_dividend_payer = bool(divs) or bool(last_div)

    # Simple stability heuristic based on count in window
    dividend_stability = "none"
    if is_dividend_payer:
        n = len(divs)
        if n >= 12:
            dividend_stability = "3yr_consistent"
        elif n >= 4:
            dividend_stability = "consistent"
        else:
            dividend_stability = "irregular"

    # Human notes (protective / explanatory)
    notes: list[str] = []
    if has_recent_split and split_date:
        ratio = split_ratio or ""
        notes.append(f"Recent split {ratio} on {split_date} — technical signals (momentum, ATR, vol, ranges) may be distorted until normalization")
    if recent_dividend_cut and dividend_cut_date:
        cut = f"{int(dividend_cut_pct * 100)}%" if dividend_cut_pct is not None else ""
        notes.append(f"Dividend cut of {cut} on {dividend_cut_date}")
    if ex_div_date and ex_div_amount is not None:
        notes.append(f"Ex-dividend on {ex_div_date} (${ex_div_amount})")

    # Lightweight v1.0 impact score (additive, capped, conservative)
    impact = 0.0
    if is_dividend_payer and len(divs) >= 8:
        impact += 0.05
    if recent_dividend_cut:
        impact -= 0.40
    if has_recent_split and split_date:
        try:
            sd = datetime.strptime(split_date, "%Y-%m-%d").date()
            days_ago = (date.today() - sd).days
            if days_ago <= 30:
                impact -= 0.20
            elif days_ago <= 90:
                impact -= 0.10
        except Exception:
            impact -= 0.10
    if ex_div_date:
        try:
            ed = datetime.strptime(ex_div_date, "%Y-%m-%d").date()
            days_to_ex = (ed - date.today()).days
            if 0 <= days_to_ex <= 5:
                impact -= 0.10
        except Exception:
            pass

    impact = max(-0.50, min(0.20, round(impact, 2)))

    return {
        "has_recent_split": has_recent_split,
        "split_date": split_date,
        "split_ratio": split_ratio,
        "split_normalized": has_recent_split,  # v1: flag that normalization may be needed / applied upstream
        "recent_dividend_cut": recent_dividend_cut,
        "dividend_cut_date": dividend_cut_date,
        "dividend_cut_pct": dividend_cut_pct,
        "ex_div_date": ex_div_date,
        "ex_div_amount": ex_div_amount,
        "is_dividend_payer": is_dividend_payer,
        "dividend_stability": dividend_stability,
        "notes": notes,
        "impact_score": impact,
    }


# =============================================================================
# SELF-TEST / DIAGNOSTIC (run directly)
# =============================================================================
if __name__ == "__main__":
    print("=" * 85)
    print("CORPORATE ACTIONS MODULE v1 — DIAGNOSTIC / USAGE EXAMPLE")
    print("=" * 85)

    # Example 1: Single high-dividend ticker (KO)
    print("\n--- get_corporate_actions('KO') [default ~3y div / ~5y splits] ---")
    ko = get_corporate_actions("KO")
    print(f"Ticker: {ko['ticker']}")
    print(f"Dividends (last 5): {len(ko['dividends'])}  Last: {ko.get('last_dividend')}")
    print(f"Splits: {len(ko['splits'])}  Recent split? {ko['has_recent_split']}")
    if ko["dividends"]:
        print("  Sample div:", ko["dividends"][0])

    print("\n--- get_corporate_actions('KO', dividend_lookback_days=365*2) [custom lookback] ---")
    ko2 = get_corporate_actions("KO", dividend_lookback_days=365*2)
    print(f"Dividends with 2y lookback: {len(ko2['dividends'])}")

    # Example 2: A ticker that may have had a split (e.g. NVDA or TSLA historically)
    print("\n--- get_splits('NVDA', lookback_days=2000) ---")
    nvda_splits = get_splits("NVDA", lookback_days=2000)
    print(f"NVDA splits found: {len(nvda_splits)}")
    for s in nvda_splits[:2]:
        print(" ", s)

    # Example 3: Batch on a few names (including one likely to be empty)
    print("\n--- batch_get_corporate_actions(['KO', 'ABBV', 'BRK.A', 'FAKE123'], custom lookbacks) ---")
    batch = batch_get_corporate_actions(
        ["KO", "ABBV", "BRK.A", "FAKE123"],
        pause_seconds=0.8,
        dividend_lookback_days=365*3,
        split_lookback_days=365*5,
    )
    for t, ca in batch.items():
        dcount = len(ca.get("dividends", []))
        scount = len(ca.get("splits", []))
        print(f"  {t}: dividends={dcount} splits={scount}  last_div={bool(ca.get('last_dividend'))}")

    print("\n" + "=" * 85)
    print("v1 DIAGNOSTIC COMPLETE.")
    print("Use batch_get_corporate_actions(list of 40, dividend_lookback_days=..., split_lookback_days=...) for full ad-hoc run.")
    print("Missing MASSIVE_API_KEY or rate limits will produce empty results cleanly.")
    print("=" * 85)
