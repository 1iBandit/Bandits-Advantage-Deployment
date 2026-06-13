"""
Universe management helpers for Bandit's Advantage v3 (Phase 3+).

Supports the two-mode design:
- Ad-hoc mode: user explicitly provides a small list of tickers via cfg.tickers.
- Scheduled / full run mode: load a core universe (from file) + optional dynamic expansion
  (top stocks and top ETFs by recent volume, fetched via Polygon grouped daily aggregates).

The build_universe function is intentionally pure and easy to test / mock.
The dynamic expansion logic lives in fetch_dynamic_universe_additions and is easy to
unit test by patching the internal _fetch_grouped_daily helper.

Additional lightweight helpers (get_universe / get_ad_hoc_universe) provide direct
file-based access to config/universe/*.csv with optional dynamic merge. These are
the recommended entry points for scripts and run_engine customizations.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import date as Date, timedelta
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv

# Ensure .env is loaded when universe.py (and thus POLYGON_API_KEY) is used directly
load_dotenv()

from engine.models.core import EngineConfig
from engine.io import readers


def build_universe(cfg: EngineConfig) -> List[str]:
    """
    Build the list of tickers to analyze for this run.

    Two-mode logic:
    - If cfg.tickers is provided (non-empty): return it directly.
      This is "ad-hoc mode" — no core universe loading, no dynamic expansion.
      Useful for quick one-off analysis on a specific set of names.

    - Otherwise (scheduled / full run mode):
      1. Load the core universe from cfg.core_universe_path (falls back to default
         data/reference/tickers.csv via readers.load_tickers).
      2. If cfg.use_dynamic_expansion is True, append additional tickers from
         the dynamic expansion stub (top liquid stocks + top ETFs by volume).

    The returned list is deduplicated and upper-cased.

    This function is pure (no I/O except what readers do, which is also configurable
    via paths) and easy to unit-test by passing different EngineConfig objects.

    Args:
        cfg: EngineConfig containing universe settings.

    Returns:
        Sorted list of uppercase ticker symbols.
    """
    # Ad-hoc mode: explicit list wins, bypass everything else
    if cfg.tickers:
        return sorted({t.upper() for t in cfg.tickers if t and t.strip()})

    # Scheduled / full-run mode
    core_path = cfg.core_universe_path
    core_tickers = readers.load_tickers(core_path)

    if not cfg.use_dynamic_expansion:
        return core_tickers

    # Dynamic expansion (now uses EngineConfig values; ETF default increased to 200 in 2025-04)
    # Stock side left at 100 per spec. The cfg values fall back to the (updated) function defaults.
    additions = fetch_dynamic_universe_additions(
        top_stocks=cfg.dynamic_top_stocks,
        top_etfs=cfg.dynamic_top_etfs,
        as_of=cfg.as_of,
    )

    # Combine and deduplicate (core first, then additions)
    combined = core_tickers + [t for t in additions if t not in core_tickers]
    return sorted(set(combined))


# Common high-volume ETFs (used for splitting stocks vs ETFs)
_COMMON_ETFS = {
    "SPY", "QQQ", "IWM", "TLT", "GLD", "EEM", "EFA", "XLF", "XLK", "XLV",
    "XLE", "XLY", "XLI", "XLB", "XLP", "XLU", "XLRE", "XLC", "VTI", "VEA",
    "VWO", "BND", "AGG", "LQD", "HYG", "JNK", "IEF", "SHY", "TBT",
}


logger = logging.getLogger(__name__)


def fetch_dynamic_universe_additions(
    top_stocks: int = 100,
    top_etfs: int = 200,   # 2025-04 change: default raised to 200 ETFs (was 20) for broader nightly/scheduled coverage via build_universe
    as_of: Optional[Date] = None,
) -> List[str]:
    """
    Fetch top volume leaders (stocks + ETFs) using Polygon's grouped daily aggregates endpoint.

    This is the production implementation used for dynamic universe expansion during
    scheduled / full-run mode.

    Strategy (conservative v1):
    - Uses the Grouped Daily endpoint for a single trading day (very efficient).
    - Sorts all tickers by volume (descending).
    - Splits into stocks vs ETFs using a small set of known high-volume ETFs.
    - Returns the top N stocks + top N ETFs (excluding any already in the core list
      is handled by the caller in build_universe).

    The function is designed to be easy to test by patching the internal
    `_fetch_grouped_daily` helper.

    NOTE (2025-04): ETF default changed to 200 (stock side remains 100). This is the
    value used by default in scheduled runs (via EngineConfig.dynamic_top_etfs when
    use_dynamic_expansion=True and no explicit override).

    Args:
        top_stocks: Maximum number of top stocks (by volume) to return. (unchanged)
        top_etfs: Maximum number of top ETFs (by volume) to return. Default now 200.
        as_of: Reference date. If None, uses yesterday.

    Returns:
        List of uppercase ticker symbols (stocks first, then ETFs).
        Empty list on any error or missing API key.
    """
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        logger.warning("POLYGON_API_KEY not set. Dynamic universe expansion disabled.")
        return []

    # Determine the date to query (use previous day if not specified)
    target_date = as_of or (Date.today() - timedelta(days=1))
    date_str = target_date.strftime("%Y-%m-%d")

    try:
        results = _fetch_grouped_daily(date_str, api_key)
    except Exception as e:
        logger.warning(f"Failed to fetch grouped daily from Polygon for {date_str}: {e}")
        return []

    if not results:
        return []

    # Filter and sort by volume (descending)
    valid = [r for r in results if r.get("v") is not None and r.get("T")]
    sorted_by_volume = sorted(valid, key=lambda x: x["v"], reverse=True)

    # Split stocks vs ETFs
    etf_list: List[str] = []
    stock_list: List[str] = []

    for item in sorted_by_volume:
        ticker = str(item["T"]).upper()
        if ticker in _COMMON_ETFS:
            etf_list.append(ticker)
        else:
            stock_list.append(ticker)

    # Take requested numbers
    selected = stock_list[:top_stocks] + etf_list[:top_etfs]

    # Deduplicate while preserving order (stocks first)
    seen = set()
    final: List[str] = []
    for t in selected:
        if t not in seen:
            seen.add(t)
            final.append(t)

    return final


def _fetch_grouped_daily(date_str: str, api_key: str) -> list[dict]:
    """
    Internal helper that calls Polygon's grouped daily endpoint using stdlib urllib.

    Easy to mock in unit tests:
        with patch("engine.pipeline.universe._fetch_grouped_daily") as mock:
            mock.return_value = [{"T": "AAPL", "v": 123456789}, ...]
    """
    url = (
        f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date_str}"
        f"?adjusted=true&apiKey={api_key}"
    )

    req = urllib.request.Request(url, headers={"User-Agent": "BanditsAdvantage/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw)
    except urllib.error.URLError as e:
        logger.warning(f"Network error calling Polygon: {e}")
        return []
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse Polygon response: {e}")
        return []

    if data.get("status") != "OK":
        logger.warning(f"Polygon grouped daily returned status: {data.get('status')}")
        return []

    return data.get("results", []) or []


# ---------------------------------------------------------------------------
# New lightweight universe helpers (additional requirement)
# ---------------------------------------------------------------------------

def get_universe(
    core_path: str = "config/universe/core_tickers.csv",
    use_dynamic_expansion: bool = False,
    dynamic_top_stocks: int = 100,
    dynamic_top_etfs: int = 200,
    as_of: Optional[Date] = None,
) -> List[str]:
    """
    Load the scheduled/core universe and optionally merge dynamic leaders.

    - Loads tickers from `config/universe/core_tickers.csv` (CSV with 'ticker' column
      or plain one-per-line; falls back to readers.load_tickers logic).
    - If `use_dynamic_expansion=True`, appends top volume stocks + ETFs fetched
      live from Polygon (using POLYGON_API_KEY). Dynamic additions are deduplicated
      against core.
    - Always returns a clean, sorted, deduplicated list of uppercase tickers
      ready to pass to ingest / scoring / run_engine.

    Missing core file: raises a clear FileNotFoundError (no silent empty).
    Dynamic fetch failures: return just the core (with warning logged inside fetch).

    This is a lightweight, reusable helper intended for run_engine, CLI scripts,
    or notebooks. It does not depend on EngineConfig.

    Example:
        tickers = get_universe(use_dynamic_expansion=True, dynamic_top_stocks=50)
        cfg = EngineConfig(tickers=tickers, data_source="polygon")
        output = run_engine(cfg)
    """
    core_p = Path(core_path)
    if not core_p.exists():
        raise FileNotFoundError(
            f"Core tickers file not found: {core_p}. "
            "Create config/universe/core_tickers.csv with a 'ticker' column "
            "(or one ticker per line) for scheduled runs."
        )

    core_tickers = readers.load_tickers(str(core_p))

    if not use_dynamic_expansion:
        return core_tickers

    additions = fetch_dynamic_universe_additions(
        top_stocks=dynamic_top_stocks,
        top_etfs=dynamic_top_etfs,
        as_of=as_of,
    )

    # Combine core first, then new additions (preserve order, dedup)
    combined = core_tickers + [t for t in additions if t not in core_tickers]
    return sorted(set(combined))


def get_ad_hoc_universe(
    ad_hoc_path: str = "config/universe/ad_hoc_tickers.csv",
    merge_core: bool = False,
    merge_dynamic: bool = False,
    core_path: Optional[str] = None,
    dynamic_top_stocks: int = 100,
    dynamic_top_etfs: int = 200,
    as_of: Optional[Date] = None,
) -> List[str]:
    """
    Load an ad-hoc/manual list of tickers for testing outside the main universe.

    - Primary: loads from `config/universe/ad_hoc_tickers.csv` (supports same format
      as core: 'ticker' column CSV or plain list).
    - If `merge_core=True`: also loads and merges the core universe (deduped).
    - If `merge_dynamic=True`: also fetches and merges current top volume leaders
      from Polygon (deduped). Useful to test a few names + some liquid names.
    - Returns clean sorted uppercase list ready for scoring.

    Missing ad-hoc file: raises clear FileNotFoundError (the point of this helper
    is the ad-hoc list you maintain for manual runs).
    Core/dynamic missing/empty: ignored gracefully if the flags are set.

    Designed for manual/ad-hoc runs (e.g. "test these 5 weird names + core").

    Example:
        tickers = get_ad_hoc_universe(merge_core=True, merge_dynamic=True)
        # or just the ad-hoc list
        tickers = get_ad_hoc_universe()
        output = run_engine(EngineConfig(tickers=tickers, data_source="polygon"))
    """
    adhoc_p = Path(ad_hoc_path)
    if not adhoc_p.exists():
        raise FileNotFoundError(
            f"Ad-hoc tickers file not found: {adhoc_p}. "
            "Create config/universe/ad_hoc_tickers.csv for manual runs. "
            "One ticker per line or with 'ticker' header."
        )

    ad_hoc_tickers = readers.load_tickers(str(adhoc_p))
    result: List[str] = list(ad_hoc_tickers)

    if merge_core:
        cpath = core_path or "config/universe/core_tickers.csv"
        try:
            core = readers.load_tickers(cpath)
            for t in core:
                if t not in result:
                    result.append(t)
        except Exception as e:  # if core also missing, don't fail the ad-hoc run
            logger.warning(f"Could not load core for merge in ad-hoc: {e}")

    if merge_dynamic:
        try:
            additions = fetch_dynamic_universe_additions(
                top_stocks=dynamic_top_stocks,
                top_etfs=dynamic_top_etfs,
                as_of=as_of,
            )
            for t in additions:
                if t not in result:
                    result.append(t)
        except Exception as e:
            logger.warning(f"Dynamic expansion failed during ad-hoc merge: {e}")

    return sorted(set(result))
