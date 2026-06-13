"""
Realized vs Expected Range Tracking (lightweight diagnostic layer).

This module provides simple, pure helper functions to compare actual
("realized") price performance against the volatility-derived expected
move ranges (12-week and 12-month) produced by the feature layer.

PURPOSE (Phase 3+ diagnostic only)
---------------------------------
- Give quick visibility into whether price action has been "in line with",
  "exceeding", or "under" the engine's own forward-looking volatility
  expectations.
- Act as a building block for future realized-performance monitoring,
  alert generation, or backtest calibration.
- `build_outlier_event(...)` provides a simple detector/builder for cases where
  the realized move greatly exceeds the engine's own expected range (OutlierEvent).
- `detect_and_build_outliers(...)` is a post-run convenience that scans a list of
  TickerScores against a realized_returns dict and emits the qualifying OutlierEvents.
- `save_outliers_to_jsonl(...)` / `load_outliers_from_jsonl(...)` provide simple JSONL
  persistence for accumulating a dataset of OutlierEvents over multiple runs.
- NOT a full historical backtesting or walk-forward framework.

DESIGN PRINCIPLES
-----------------
- Extremely lightweight: the caller supplies realized returns when they
  are available (from a later data fetch, portfolio records, etc.).
- No I/O inside the functions.
- Returns simple, human-readable status strings plus optional numeric
  deviation for downstream use or display.
- Fully backward compatible — all new fields default to None and all
  new parameters have safe defaults.

The current categorization is intentionally simple. It can be refined
later (multi-band, probability-weighted, regime-aware, etc.) without
breaking existing call sites.

OUTLIER PIPELINE (Phase 4+ foundation)
--------------------------------------
The outlier system identifies "unexplained" large moves — cases where a ticker's
realized performance significantly exceeds the engine's own expected range
(derived from pre-event volatility/features) even after accounting for
acceleration signals and news.

Use it to:
- Detect surprises / potential regime shifts after a run
- Accumulate a long-term dataset of outliers for calibration and model improvement

Main entry points (lightweight + pure except for JSONL I/O):
- `build_outlier_event(ticker, as_of, ticker_score, realized_move, threshold_multiplier=2.0)`
  -> Optional[OutlierEvent]
  Single-ticker builder. Returns None if the move does not exceed the multiplier
  threshold (default 2x). Captures pre-event feature snapshot + accel/news fields.

- `detect_and_build_outliers(scores, realized_returns, threshold_multiplier=2.0)`
  -> List[OutlierEvent]
  Post-run batch helper. Pass EngineOutput.scores (or list of TickerScore) + a
  {ticker: realized_move} dict (e.g. 12w returns collected separately).

- `save_outliers_to_jsonl(events, path)` / `load_outliers_from_jsonl(path)`
  Append-only JSONL persistence (date-safe, defensive on corrupt lines) so you
  can accumulate surprises across many runs.

Typical flow after `run_engine(...)` (once you have realized returns):
    realized = {"AAPL": 27.4, "MSFT": 4.2, ...}
    outliers = detect_and_build_outliers(output.scores, realized)
    if outliers:
        save_outliers_to_jsonl(outliers, "surprises.jsonl")
    # later analysis
    loaded = load_outliers_from_jsonl("surprises.jsonl")

See the runnable mini-workflow in the `if __name__ == "__main__":` block below.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any, Optional, Dict, List
import json
import sys

from engine.models.core import TickerScore, OutlierEvent

# v1.0 CA context builder for sanity checks in outliers
try:
    from engine.pipeline.steps.corporate_actions import build_corporate_action_context
except Exception:
    build_corporate_action_context = None


@dataclass
class RangeComparison:
    """
    Lightweight result of comparing realized return to an expected range.

    Attributes:
        horizon:            "12w" or "12m"
        expected_range_pct: The raw expected move range (percentage points)
        realized_return_pct: The actual return over the matching horizon, or None
        status:             One of:
                            - "No Realized Data"
                            - "In Range"
                            - "Exceeding"
                            - "Underperforming"
        deviation:          (abs(realized) - expected) / expected, or None.
                            Positive = larger move than expected.
        notes:              Short human-readable explanation.
    """
    horizon: str
    expected_range_pct: float
    realized_return_pct: Optional[float]
    status: str
    deviation: Optional[float] = None
    notes: str = ""


def compare_realized_to_expected(
    expected_range: float,
    realized_return: Optional[float] = None,
    *,
    horizon: str = "12w",
    tolerance: float = 0.85,
) -> RangeComparison:
    """
    Compare a realized return against a single expected move range.

    This is the core lightweight diagnostic primitive.

    Args:
        expected_range: Expected range percentage for the horizon
                        (e.g. 12.5 for ±12.5%).
        realized_return: Actual percentage return over the same horizon.
                         Positive or negative. If None, status will be
                         "No Realized Data".
        horizon: Label for the horizon ("12w", "12m", etc.). Used only
                 for output labeling.
        tolerance: Fraction of the expected range that still counts as
                   "In Range" (default 0.85 = 85%). Values below this
                   threshold but above zero are labeled "Underperforming".

    Returns:
        RangeComparison dataclass with status and deviation.

    Status Rules (simple v1):
        - "No Realized Data" : realized_return was None
        - "Exceeding"        : |realized| > expected_range
        - "In Range"         : tolerance * expected <= |realized| <= expected
        - "Underperforming"  : 0 < |realized| < tolerance * expected

    The function is pure and has no side effects.
    """
    if realized_return is None:
        return RangeComparison(
            horizon=horizon,
            expected_range_pct=round(float(expected_range), 2),
            realized_return_pct=None,
            status="No Realized Data",
            deviation=None,
            notes=f"No realized return supplied for {horizon} comparison.",
        )

    exp = abs(float(expected_range))
    real = abs(float(realized_return))

    if exp <= 0.0:
        status = "No Expected Range"
        deviation = None
    elif real > exp:
        status = "Exceeding"
        deviation = round((real - exp) / exp, 3)
    elif real >= exp * tolerance:
        status = "In Range"
        deviation = round((real - exp) / exp, 3)
    else:
        status = "Underperforming"
        deviation = round((real - exp) / exp, 3)

    sign = "+" if realized_return >= 0 else ""
    notes = (
        f"{horizon}: realized {sign}{realized_return:.1f}% vs "
        f"expected +/-{expected_range:.1f}% = {status}"
    )

    return RangeComparison(
        horizon=horizon,
        expected_range_pct=round(exp, 2),
        realized_return_pct=round(float(realized_return), 2),
        status=status,
        deviation=deviation,
        notes=notes,
    )


def compare_realized_ranges(
    expected_12w: float,
    expected_12m: float,
    realized_12w: Optional[float] = None,
    realized_12m: Optional[float] = None,
    tolerance: float = 0.85,
) -> dict[str, RangeComparison]:
    """
    Convenience wrapper that returns comparisons for both 12w and 12m horizons.

    Useful when populating TickerScore objects or building summary reports.

    Returns:
        dict with keys "12w" and "12m" mapping to RangeComparison objects.
    """
    return {
        "12w": compare_realized_to_expected(
            expected_range=expected_12w,
            realized_return=realized_12w,
            horizon="12w",
            tolerance=tolerance,
        ),
        "12m": compare_realized_to_expected(
            expected_range=expected_12m,
            realized_return=realized_12m,
            horizon="12m",
            tolerance=tolerance,
        ),
    }


def build_outlier_event(
    ticker: str,
    as_of: date,
    ticker_score: TickerScore,
    realized_move: float,
    threshold_multiplier: float = 2.0,
    corporate_actions: Optional[dict[str, dict]] = None,  # v1.0 for CA sanity / attribution
) -> Optional[OutlierEvent]:
    """
    Create an OutlierEvent if the realized move significantly exceeds
    the engine's expected range (using 12w by default).

    Uses the raw_expected_range_12w from the TickerScore as the baseline
    expectation. If |realized_move| > threshold_multiplier * |expected|,
    an OutlierEvent is built with a snapshot of pre-event features plus
    the acceleration and news signals that were available.

    Returns None if the move does not qualify as an outlier (i.e. within
    the multiplier threshold, or no expected range available).

    v2: opportunistically adds `regime` tag (Trending/Choppy/High_Vol/Low_Vol/Unknown)
    derived from pre-event momentum/breadth/volatility signals in the TickerScore.

    This is a pure builder / detector. It does not perform I/O.
    """
    if ticker_score is None:
        return None

    # Prefer 12w expected range (primary horizon for these diagnostics)
    expected = float(getattr(ticker_score, "raw_expected_range_12w", 0.0) or 0.0)
    if expected <= 0.0:
        return None

    real = float(realized_move)
    exp_abs = abs(expected)
    real_abs = abs(real)

    if real_abs <= threshold_multiplier * exp_abs:
        # Not a significant outlier
        return None

    delta = real - expected

    # Snapshot of key pre-event features (for later analysis / ML on surprises)
    pre_event_features: Dict[str, Any] = {
        "rsi": float(getattr(ticker_score, "rsi", 0.0)),
        "atr_pct": float(getattr(ticker_score, "atr_pct", 0.0)),
        "adx": float(getattr(ticker_score, "adx", 0.0)),
        "rs_vs_spy": float(getattr(ticker_score, "rs_vs_spy", 0.0)),
        "relative_breadth_score": float(getattr(ticker_score, "relative_breadth_score", 50.0)),
        "momentum_pulse": float(getattr(ticker_score, "momentum_pulse", 0.0)),
        "short_term_movement_intensity": float(getattr(ticker_score, "short_term_movement_intensity", 0.0)),
        "raw_expected_range_12w": expected,
        "raw_expected_range_12m": float(getattr(ticker_score, "raw_expected_range_12m", 0.0)),
        "rsi_acceleration": float(getattr(ticker_score, "rsi_acceleration", 0.0)),
        "volatility_expansion_flag": float(getattr(ticker_score, "volatility_expansion_flag", 0.0)),
    }

    # Opportunistically pull the accel / news signals that were present
    accel_rsi = getattr(ticker_score, "rsi_acceleration", None)
    vol_exp_flag = getattr(ticker_score, "volatility_expansion_flag", None)

    news_encoded: Optional[str] = None
    notes_text = getattr(ticker_score, "notes", "") or ""
    if "NewsPulse:" in notes_text:
        try:
            after = notes_text.split("NewsPulse:", 1)[1]
            token = after.split("|", 1)[0].strip()
            # token is usually "N45 -> 0.0% impact" or just "N45"
            news_encoded = token.split("->", 1)[0].strip() if "->" in token else token
        except Exception:
            news_encoded = None

    # v2: lightweight regime tag from pre-event signals (opportunistic, no extra data needed)
    # Uses ticker's own momentum/breadth/vol as proxy for market regime at event time.
    def _regime_from_score(score: TickerScore) -> str:
        mp = float(getattr(score, "momentum_pulse", 0.0))
        br = float(getattr(score, "relative_breadth_score", 50.0))
        atr = float(getattr(score, "atr_pct", 0.0))
        stm = float(getattr(score, "short_term_movement_intensity", 0.0))
        if atr > 4.0 or stm > 40.0:
            return "High_Vol"
        if mp > 2.0 and br > 60.0:
            return "Trending"
        if mp < -1.0 or br < 40.0 or stm > 30.0:
            return "Choppy"
        if atr < 1.0:
            return "Low_Vol"
        return "Unknown"

    regime = _regime_from_score(ticker_score)

    # Build explanatory notes, reusing the comparison primitive for consistency
    comparison = compare_realized_to_expected(
        expected_range=expected,
        realized_return=realized_move,
        horizon="12w",
        tolerance=1.0 / threshold_multiplier,
    )
    event_notes = (
        f"OUTLIER x{threshold_multiplier:.1f}: {comparison.notes} "
        f"(delta {delta:+.1f}%) [regime={regime}]"
    )

    # === v1.0 Corporate Action sanity / attribution (protective, not scoring driver) ===
    ca_context: Optional[dict] = None
    dividend_cut_info: Optional[dict] = None
    if corporate_actions:
        ca = corporate_actions.get(ticker.upper()) or corporate_actions.get(ticker)
        if ca and build_corporate_action_context is not None:
            try:
                ca_context = build_corporate_action_context(ca)
            except Exception:
                ca_context = None

    if ca_context:
        ca_notes: list[str] = []
        if ca_context.get("has_recent_split"):
            sd = ca_context.get("split_date")
            ratio = ca_context.get("split_ratio") or ""
            ca_notes.append(f"recent split {ratio} on {sd} (technical distortion likely)")
        if ca_context.get("recent_dividend_cut"):
            ddate = ca_context.get("dividend_cut_date")
            dpct = ca_context.get("dividend_cut_pct")
            cut_str = f"{int(dpct*100)}%" if dpct is not None else ""
            ca_notes.append(f"dividend cut {cut_str} on {ddate}")
            dividend_cut_info = {"date": ddate, "pct": dpct}
        if ca_context.get("ex_div_date"):
            ca_notes.append(f"ex-div on {ca_context.get('ex_div_date')}")
        if ca_notes:
            event_notes += " [CA: " + "; ".join(ca_notes) + "]"

    return OutlierEvent(
        ticker=ticker,
        as_of=as_of,
        expected_move=expected,
        realized_move=realized_move,
        delta=delta,
        pre_event_features=pre_event_features,
        rsi_acceleration=accel_rsi,
        volatility_expansion_flag=vol_exp_flag,
        news_encoded=news_encoded,
        regime=regime,
        notes=event_notes,
        corporate_action_context=ca_context,
        dividend_cut=dividend_cut_info,
    )


def detect_and_build_outliers(
    scores: List[TickerScore],
    realized_returns: Dict[str, float],
    threshold_multiplier: float = 2.0,
    corporate_actions: Optional[dict[str, dict]] = None,  # v1.0 pass-through for CA sanity
) -> List[OutlierEvent]:
    """
    Scan a list of TickerScore objects and build OutlierEvents for any
    tickers where the realized move significantly exceeds the expected range.

    realized_returns: mapping of ticker (uppercased) -> realized move (e.g. 12w return %).
    Only tickers present in realized_returns will be considered.

    Delegates to build_outlier_event for the per-ticker logic (using 12w expected
    range by default inside that helper).

    Returns a list of OutlierEvent (possibly empty). Pure function, no side effects.
    """
    events: List[OutlierEvent] = []
    if not scores or not realized_returns:
        return events

    for score in scores:
        ticker = getattr(score, "ticker", None)
        if not ticker or ticker not in realized_returns:
            continue
        realized_move = realized_returns[ticker]
        event = build_outlier_event(
            ticker=ticker,
            as_of=getattr(score, "as_of", None) or date.today(),
            ticker_score=score,
            realized_move=realized_move,
            threshold_multiplier=threshold_multiplier,
            corporate_actions=corporate_actions,
        )
        if event is not None:
            events.append(event)

    return events


def save_outliers_to_jsonl(events: List[OutlierEvent], path: str | Path) -> None:
    """
    Append (or create) a JSONL file containing the given OutlierEvents.

    Each OutlierEvent is serialized to one JSON object per line using
    dataclasses.asdict, with special handling for the `as_of` date field
    (converted to ISO format string 'YYYY-MM-DD' for portability).

    The file is opened in append mode ('a'), so repeated calls accumulate
    events without overwriting previous ones. Parent directories are created
    if they do not exist.

    Lightweight and defensive: skips None events silently.
    """
    if not events:
        return

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("a", encoding="utf-8") as f:
        for ev in events:
            if ev is None:
                continue
            d = asdict(ev)
            # Serialize date to ISO string
            if isinstance(d.get("as_of"), date):
                d["as_of"] = d["as_of"].isoformat()
            # Ensure pre_event_features is a plain dict (it should be)
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def load_outliers_from_jsonl(path: str | Path) -> List[OutlierEvent]:
    """
    Load OutlierEvents from a JSONL file (one JSON object per line).

    Reconstructs OutlierEvent instances. The `as_of` field is parsed back
    from ISO string to datetime.date.

    Defensive:
    - Skips blank lines and lines that fail to parse as JSON.
    - Skips lines that fail to construct a valid OutlierEvent (e.g. missing
      required fields or type errors) and continues.
    - Returns an empty list if the file does not exist.

    Does not raise on individual bad lines (logs a warning to stderr for
    debugging if a line is skipped).
    """
    p = Path(path)
    if not p.exists():
        return []

    events: List[OutlierEvent] = []
    with p.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Warning: skipping invalid JSON on line {line_num}: {e}", file=sys.stderr)
                continue

            # Reconstruct date if present as string
            if isinstance(d.get("as_of"), str):
                try:
                    d["as_of"] = date.fromisoformat(d["as_of"])
                except ValueError:
                    # leave as-is or skip? try to let dataclass handle, but better skip if bad
                    print(f"Warning: skipping line {line_num} with unparseable date", file=sys.stderr)
                    continue

            try:
                ev = OutlierEvent(**d)
                events.append(ev)
            except (TypeError, ValueError) as e:
                print(f"Warning: skipping line {line_num} (failed to build OutlierEvent): {e}", file=sys.stderr)
                continue

    return events


# Quick demo when run directly
if __name__ == "__main__":
    print("=== Realized vs Expected Range Tracking (lightweight demo) ===\n")

    # Example with realized data
    r1 = compare_realized_to_expected(12.5, 9.8, horizon="12w")
    print(r1)

    r2 = compare_realized_to_expected(28.0, 34.2, horizon="12m")
    print(r2)

    # Batch helper
    batch = compare_realized_ranges(12.5, 28.0, realized_12w=-4.0, realized_12m=31.0)
    print("\nBatch 12w status:", batch["12w"].status)
    print("Batch 12m status:", batch["12m"].status)

    print("\nWhen no realized data is supplied:")
    print(compare_realized_to_expected(15.0, None, horizon="12w"))

    # Outlier builder demo (requires a TickerScore with expected ranges populated)
    print("\n=== build_outlier_event demo ===")
    from engine.models.core import TickerScore
    from datetime import date as Date

    # Minimal TickerScore with an "explosive" realized move
    demo_score = TickerScore(
        ticker="EXPL",
        as_of=Date(2025, 4, 10),
        close=150.0,
        rsi=55.0,
        atr_pct=2.1,
        adx=22.0,
        rs_vs_spy=1.05,
        relative_breadth_score=62.0,
        raw_expected_range_12w=9.5,
        raw_expected_range_12m=22.0,
        short_term_movement_intensity=18.0,
        momentum_pulse=1.4,
        rsi_acceleration=2.8,
        volatility_expansion_flag=1.0,
        bandits_rocket=3.5,
        notes="Abstention: Trade Eligible | Rocket: +3.5 (bullish) | NewsPulse: N52 -> 1.2% impact",
    )

    outlier = build_outlier_event(
        ticker="EXPL",
        as_of=Date(2025, 4, 10),
        ticker_score=demo_score,
        realized_move=27.4,   # >> 2x the 9.5 expected
        threshold_multiplier=2.0,
    )
    if outlier:
        print("OutlierEvent created:")
        print("  ticker:", outlier.ticker)
        print("  delta:", outlier.delta)
        print("  news_encoded:", outlier.news_encoded)
        print("  accel_rsi:", outlier.rsi_acceleration)
        print("  notes:", outlier.notes)
    else:
        print("No outlier (move not large enough).")

    # Non-outlier case
    normal = build_outlier_event(
        ticker="NORMAL",
        as_of=Date(2025, 4, 10),
        ticker_score=demo_score,
        realized_move=12.0,  # inside 2x
        threshold_multiplier=2.0,
    )
    print("Non-outlier returned None?", normal is None)

    # Batch post-run detector demo
    print("\n=== detect_and_build_outliers demo ===")
    demo_score2 = TickerScore(
        ticker="QUIET",
        as_of=Date(2025, 4, 10),
        close=100.0,
        rsi=50.0,
        atr_pct=1.5,
        adx=15.0,
        rs_vs_spy=0.98,
        relative_breadth_score=48.0,
        raw_expected_range_12w=8.0,
        raw_expected_range_12m=18.0,
        short_term_movement_intensity=12.0,
        momentum_pulse=0.2,
        rsi_acceleration=0.1,
        volatility_expansion_flag=0.0,
        bandits_rocket=0.5,
        notes="Abstention: Observe / No Trade | Rocket: +0.5 (bullish) | NewsPulse: N45 -> 0.0% impact",
    )

    realized_map = {
        "EXPL": 27.4,   # will trigger outlier (2.9x)
        "QUIET": 3.5,   # will not (0.44x)
        "MISSING": 99.9,  # no matching score
    }

    outliers = detect_and_build_outliers(
        scores=[demo_score, demo_score2],
        realized_returns=realized_map,
        threshold_multiplier=2.0,
    )
    print(f"Found {len(outliers)} outlier event(s):")
    for ev in outliers:
        print(f"  {ev.ticker}: delta={ev.delta:.1f}, notes={ev.notes[:80]}...")

    # Persistence demo (JSONL round-trip)
    print("\n=== JSONL persistence demo (save/load) ===")
    import tempfile
    from pathlib import Path as _Path
    with tempfile.TemporaryDirectory() as tmp:
        jsonl_path = _Path(tmp) / "outliers.jsonl"
        # save
        save_outliers_to_jsonl(outliers, jsonl_path)
        print(f"Saved {len(outliers)} events to {jsonl_path}")
        # load
        loaded = load_outliers_from_jsonl(jsonl_path)
        print(f"Loaded {len(loaded)} events back")
        if loaded:
            print(f"  First loaded: {loaded[0].ticker} delta={loaded[0].delta}")
        # append another
        if outliers:
            save_outliers_to_jsonl([outliers[0]], jsonl_path)
        loaded2 = load_outliers_from_jsonl(jsonl_path)
        print(f"After append, total lines loaded: {len(loaded2)}")

    # =============================================================================
    # Complete mini workflow example (copy-paste friendly)
    # =============================================================================
    print("\n" + "="*60)
    print("COMPLETE MINI WORKFLOW EXAMPLE")
    print("="*60)
    print("Creates synthetic TickerScores, runs detection, persists to JSONL,")
    print("loads them back, and prints a summary of outliers found.\n")

    from engine.models.core import TickerScore
    from datetime import date as Date
    import tempfile
    from pathlib import Path

    # 1. Create a couple of synthetic TickerScore objects (as if from run_engine)
    score1 = TickerScore(
        ticker="SURPRISE",
        as_of=Date(2025, 4, 10),
        close=142.0,
        rsi=62.0,
        atr_pct=2.8,
        adx=28.0,
        rs_vs_spy=1.15,
        relative_breadth_score=71.0,
        raw_expected_range_12w=8.2,
        raw_expected_range_12m=19.5,
        short_term_movement_intensity=24.0,
        momentum_pulse=2.1,
        rsi_acceleration=3.4,
        volatility_expansion_flag=1.0,
        bandits_rocket=4.8,
        notes="Abstention: Trade Eligible | Rocket: +4.8 (bullish) | NewsPulse: N62+ -> 2.1% impact",
    )

    score2 = TickerScore(
        ticker="EXPECTED",
        as_of=Date(2025, 4, 10),
        close=98.5,
        rsi=48.0,
        atr_pct=1.4,
        adx=14.0,
        rs_vs_spy=0.95,
        relative_breadth_score=52.0,
        raw_expected_range_12w=7.8,
        raw_expected_range_12m=17.0,
        short_term_movement_intensity=11.0,
        momentum_pulse=0.3,
        rsi_acceleration=0.2,
        volatility_expansion_flag=0.0,
        bandits_rocket=0.4,
        notes="Abstention: Minimal Direction | Rocket: +0.4 (bullish) | NewsPulse: N45 -> 0.0% impact",
    )

    scores = [score1, score2]

    # 2. Call detect_and_build_outliers with realized returns (collected separately)
    realized_returns = {
        "SURPRISE": 24.7,   # >> 2x the 8.2% expected -> outlier
        "EXPECTED": 6.1,    # within 2x -> no outlier
    }

    outliers = detect_and_build_outliers(
        scores=scores,
        realized_returns=realized_returns,
        threshold_multiplier=2.0,
    )

    # 3. Save + load via JSONL (accumulates over time)
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_file = Path(tmpdir) / "my_surprises.jsonl"

        save_outliers_to_jsonl(outliers, jsonl_file)
        print(f"Saved {len(outliers)} outlier event(s) to {jsonl_file}")

        loaded_outliers = load_outliers_from_jsonl(jsonl_file)
        print(f"Loaded {len(loaded_outliers)} outlier event(s) back from JSONL")

        # 4. Print a summary of any outliers found
        print("\n--- Outlier Summary ---")
        if not loaded_outliers:
            print("No outliers found.")
        else:
            for ev in loaded_outliers:
                print(f"  {ev.ticker} on {ev.as_of}:")
                print(f"    expected={ev.expected_move:.1f}%, realized={ev.realized_move:.1f}%")
                print(f"    delta={ev.delta:+.1f}% (x{abs(ev.realized_move)/max(ev.expected_move, 0.01):.1f} expected)")
                print(f"    accel_rsi={ev.rsi_acceleration}, vol_exp={ev.volatility_expansion_flag}")
                print(f"    news={ev.news_encoded}")
                print(f"    pre_event: {ev.pre_event_features}")
                print(f"    notes: {ev.notes}")
                print()

    print("Mini workflow complete. Copy the block above for your own runs.")
    print("="*60)
