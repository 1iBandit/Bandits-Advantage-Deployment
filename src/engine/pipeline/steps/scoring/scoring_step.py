"""
Scoring Step / Adapter for Bandit's Advantage v3 (Phase 3).

This module provides a clean, high-level function that takes Phase 2
`TickerFeatures` and produces fully populated `TickerScore` objects
with the Phase 3 scoring results applied (final_rank, abstention status,
and optionally Bandit's Rocket v3.1).

It follows the same clean, pure, and well-documented style as the
feature orchestrator in `features/compute_features.py`.

This acts as the bridge between the feature computation layer and
the core `TickerScore` model used by the rest of the engine.

Example usage (single ticker adapter):

    from engine.pipeline.steps.scoring.scoring_step import apply_scoring
    from engine.pipeline.steps.features.compute_features import TickerFeatures
    from datetime import date

    ticker_features: TickerFeatures = ...  # from compute_features
    universe: list[TickerFeatures] = [ticker_features, ...]

    score = apply_scoring(
        features=ticker_features,
        ticker="AAPL",
        as_of=date.today(),
        close=227.5,
        universe=universe,
        include_rocket=True
    )

    print(score.final_rank)
    print(score.bandits_rocket)
    print(score.notes)  # contains abstention status


Pipeline-level usage (thin step after the feature step):

    # Preferred (new canonical API - Phase 3)
    from engine.pipeline.steps.scoring.scoring_step import scoring_step
    from engine.pipeline.steps.features.compute_features import TickerFeatures
    from engine.models.core import EngineConfig

    features: dict[str, TickerFeatures] = {...}   # from feature computation
    cfg = EngineConfig(...)

    scored = scoring_step(features, cfg)          # uses cfg.scoring internally

    # Legacy API (still available during transition)
    from engine.pipeline.steps.scoring.scoring_step import legacy_scoring_step

    legacy_scores = legacy_scoring_step(old_feature_scores_list, config=cfg)
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Sequence, Union, Optional

from engine.models.core import TickerScore, EngineConfig

from .score_ticker import score_ticker, TickerFeatures
from .final_rank import calculate_final_ranks
from .abstention import get_abstention_status
from .rocket import compute_rocket_score
from .scoring_config import ScoringConfig
from .news_pulse import compute_news_pulse, apply_news_pulse
from datetime import date as _date  # avoid name clash
import pandas as pd  # for optional price context
from .expected_range import compare_realized_to_expected


__all__ = ["apply_scoring", "scoring_step"]


def _extract_features(features: TickerFeatures | dict[str, Any]) -> dict[str, float]:
    """Convert TickerFeatures or dict into a plain dict of feature values."""
    if isinstance(features, dict):
        return {k: float(v) for k, v in features.items() if isinstance(v, (int, float))}
    # Assume it's a dataclass-like object with the Phase 2 feature attributes
    return {
        "rsi": float(features.rsi),
        "atr_pct": float(features.atr_pct),
        "adx": float(features.adx),
        "rs_vs_spy": float(features.rs_vs_spy),
        "relative_breadth_score": float(features.relative_breadth_score),
        "raw_expected_range_12w": float(features.expected_range_12w),
        "raw_expected_range_12m": float(features.expected_range_12m),
        "short_term_movement_intensity": float(features.short_term_movement_intensity),
        "momentum_pulse": float(features.momentum_pulse),
        "rsi_acceleration": float(getattr(features, "rsi_acceleration", 0.0)),
        "volatility_expansion_flag": float(getattr(features, "volatility_expansion_flag", 0.0)),
    }


def apply_scoring(
    features: TickerFeatures | dict[str, Any],
    ticker: str,
    as_of: date,
    close: float,
    universe: Optional[Sequence[TickerFeatures | dict[str, Any]]] = None,
    include_rocket: bool = False,
    config: Optional[ScoringConfig] = None,
    # === New lightweight realized-vs-expected parameters (all optional) ===
    realized_12w: Optional[float] = None,
    realized_12m: Optional[float] = None,
    catalyst_strength: Optional[float] = None,  # for Catalyst Override in live/single use
) -> TickerScore:
    """
    Apply scoring logic to a ticker's features and return a populated TickerScore.

    This is the recommended function for the scoring step in the pipeline.
    It computes final_rank (when universe is provided), abstention status,
    and optionally the Bandit's Rocket v3.1 score, then assembles everything
    into a full TickerScore object.

    Args:
        features: The Phase 2 features for this ticker.
                  Can be a TickerFeatures instance or a plain dict.
        ticker: The ticker symbol (e.g. "AAPL").
        as_of: The date of the analysis.
        close: The latest close price for the ticker.
        universe: Optional list of features for the full universe of tickers.
                  Required to compute a meaningful cross-sectional final_rank.
        include_rocket: If True, also computes and populates the Bandit's Rocket
                        v3.1 score.
        config: Optional ScoringConfig passed through to the underlying scoring functions.
        realized_12w: Optional realized return (percentage) over the last ~12 weeks.
                      When supplied, range_status_12w will be populated using the
                      lightweight compare_realized_to_expected() helper.
        realized_12m: Optional realized return (percentage) over the last ~12 months.
                      When supplied, range_status_12m will be populated.

    Returns:
        A fully populated TickerScore with:
            - All Phase 2 feature values copied from the input
            - final_rank (if universe was provided)
            - bandits_rocket (if include_rocket was True)
            - abstention status stored in the notes field
            - realized_* and range_status_* fields (only when realized returns supplied)

    Notes:
        - This function is pure (no I/O or side effects).
        - It reuses the existing pure scoring helpers for consistency and testability.
        - Designed to be easily composed after the feature computation step.
        - The realized vs expected logic is deliberately lightweight and diagnostic.
          It is intended for future use by callers that have access to forward or
          subsequent realized performance data. No historical price series are
          required inside this function.
    """
    # Compute the scoring signals using the existing pure helpers
    scoring_result = score_ticker(
        features=features,
        universe=universe,
        include_rocket=include_rocket,
        config=config,
    )

    # Extract the base feature values
    feature_dict = _extract_features(features)

    # Build the TickerScore
    score = TickerScore(
        ticker=ticker,
        as_of=as_of,
        close=close,
        rsi=feature_dict.get("rsi", 0.0),
        atr_pct=feature_dict.get("atr_pct", 0.0),
        adx=feature_dict.get("adx", 0.0),
        rs_vs_spy=feature_dict.get("rs_vs_spy", 0.0),
        relative_breadth_score=feature_dict.get("relative_breadth_score", 50.0),
        raw_expected_range_12w=feature_dict.get("raw_expected_range_12w", 0.0),
        raw_expected_range_12m=feature_dict.get("raw_expected_range_12m", 0.0),
        short_term_movement_intensity=feature_dict.get("short_term_movement_intensity", 0.0),
        momentum_pulse=feature_dict.get("momentum_pulse", 0.0),
        # Acceleration v1 (populated if present in feature_dict; defaults safe for older dicts)
        rsi_acceleration=feature_dict.get("rsi_acceleration", 0.0),
        volatility_expansion_flag=feature_dict.get("volatility_expansion_flag", 0.0),
        # Populate Phase 3 scoring results
        final_rank=scoring_result.final_rank,
        bandits_rocket=scoring_result.rocket_score,
        # Store abstention status in notes for now (no dedicated field in TickerScore yet)
        notes=f"Abstention: {scoring_result.abstention_status}",
        # === Realized vs Expected diagnostics (populated only when data supplied) ===
        realized_12w_return=realized_12w,
        realized_12m_return=realized_12m,
        range_status_12w=(
            compare_realized_to_expected(
                expected_range=feature_dict.get("raw_expected_range_12w", 0.0),
                realized_return=realized_12w,
                horizon="12w",
            ).status
            if realized_12w is not None
            else None
        ),
        range_status_12m=(
            compare_realized_to_expected(
                expected_range=feature_dict.get("raw_expected_range_12m", 0.0),
                realized_return=realized_12m,
                horizon="12m",
            ).status
            if realized_12m is not None
            else None
        ),
        # Catalyst strength for override (optional, enables the logic outside replay)
        catalyst_strength_score=catalyst_strength,
    )

    return score


def legacy_scoring_step(
    feature_scores: List[TickerScore],
    config: Optional[EngineConfig] = None,
    include_rocket: bool = False,
    scoring_config: Optional[ScoringConfig] = None,
    # === New lightweight realized-vs-expected parameters (passed through) ===
    realized_12w: Optional[float] = None,
    realized_12m: Optional[float] = None,
) -> List[TickerScore]:
    """
    Thin pipeline-level scoring step.

    This is the direct counterpart to `compute_features()` in the features step.
    It takes the list of TickerScore objects produced by the feature step
    (which contain all Phase 2 features + identity) and enriches them with
    Phase 3 scoring results (final_rank, abstention status in notes, and
    optionally Bandit's Rocket v3.1).

    It performs cross-sectional ranking across the full list.

    Args:
        feature_scores: List of TickerScore from the feature computation step.
                        Each must have the Phase 2 feature fields populated.
        config: Optional EngineConfig (kept for future pipeline-level parameterization).
        include_rocket: Whether to compute and populate the Bandit's Rocket
                        v3.1 score for each ticker.
        scoring_config: Optional ScoringConfig passed down to all scoring functions
                        (abstention thresholds, rocket weights, final rank weights, etc.).
        realized_12w: Optional realized 12-week return (percentage). When provided,
                      the corresponding range_status_12w will be computed for every ticker.
        realized_12m: Optional realized 12-month return (percentage).

    Returns:
        List of enriched TickerScore objects in the same order as input.

    Notes:
        The realized_12w / realized_12m values (when supplied) are applied
        uniformly to every ticker in the list. This is the simplest useful
        form for batch/diagnostic usage. Per-ticker realized values can be
        supplied by calling apply_scoring() individually instead.
    """
    if not feature_scores:
        return []

    # Build a parallel list of feature dicts for the universe (used for ranking)
    universe_features: List[Dict[str, Any]] = []
    for s in feature_scores:
        feat = {
            "rsi": s.rsi,
            "atr_pct": s.atr_pct,
            "adx": s.adx,
            "rs_vs_spy": s.rs_vs_spy,
            "relative_breadth_score": s.relative_breadth_score,
            "expected_range_12w": s.raw_expected_range_12w,
            "expected_range_12m": s.raw_expected_range_12m,
            "short_term_movement_intensity": s.short_term_movement_intensity,
            "momentum_pulse": s.momentum_pulse,
        }
        universe_features.append(feat)

    enriched: List[TickerScore] = []
    for s, feat_dict in zip(feature_scores, universe_features):
        # Use the single-ticker adapter (which handles ranking against the universe + abstention + optional rocket)
        scored = apply_scoring(
            features=feat_dict,
            ticker=s.ticker,
            as_of=s.as_of,
            close=s.close,
            universe=universe_features,
            include_rocket=include_rocket,
            config=scoring_config,
            realized_12w=realized_12w,
            realized_12m=realized_12m,
        )
        enriched.append(scored)

    return enriched


# =============================================================================
# New Primary Pipeline-Level Scoring Step (Phase 3 design)
# =============================================================================

def scoring_step(
    features: dict[str, TickerFeatures],
    cfg: EngineConfig,
    *,
    prices: dict[str, pd.DataFrame] | None = None,
    as_of: date | None = None,
    identity: dict[str, dict[str, Any]] | None = None,
    catalysts: dict[str, float] | None = None,  # per-ticker catalyst_strength_score for override (live runs)
) -> dict[str, TickerScore]:
    """
    Primary pipeline-level scoring step (Phase 3 design - canonical version).

    This is the recommended function for the main engine pipeline:
        ingest → compute_features → scoring_step → postprocess → export

    It reads all scoring configuration from the nested `cfg.scoring`.
    After computing the core Rocket score, it also runs the News Pulse layer
    (`compute_news_pulse` + `apply_news_pulse`) and records a compact diagnostic.

    Identity data (close + as_of) can now be supplied cleanly via:
    - `prices`: the raw price DataFrames from the ingest step (most common)
    - `identity`: a lightweight per-ticker dict (for callers without full DataFrames)
    - Fallbacks from `cfg.as_of`
      (they already exist on the model).
    - The function is pure (no I/O, no mutation of inputs).

    Args:
        features: Mapping of ticker -> TickerFeatures.
        cfg: The full EngineConfig (reads from the nested `cfg.scoring`).
        prices: Optional raw price DataFrames (from ingest). If provided,
                the latest Close will be used for each ticker.
        as_of: Optional analysis date. Falls back to cfg.as_of or today.
        identity: Optional lightweight per-ticker identity:
                  {"AAPL": {"close": 227.5, "as_of": date(...)}, ...}
        catalysts: Optional dict ticker -> catalyst_strength_score (float). When supplied,
                   populates TickerScore.catalyst_strength_score so the Catalyst Override
                   can fire during regular (non-replay) engine runs.

    Returns:
        dict[str, TickerScore] with complete objects (including close and as_of).
        Abstention status, Rocket score (after News Pulse), and a compact
        NewsPulse diagnostic are placed in `.notes` (conservative strategy).
    """
    if not features:
        return {}

    scoring_cfg: ScoringConfig = getattr(cfg, "scoring", None) or ScoringConfig()

    # Prepare feature list for cross-sectional ranking
    tickers = list(features.keys())
    feature_list: List[Dict[str, Any]] = []
    for t in tickers:
        f = features[t]
        feature_list.append({
            "rsi": float(f.rsi),
            "atr_pct": float(f.atr_pct),
            "adx": float(f.adx),
            "rs_vs_spy": float(f.rs_vs_spy),
            "relative_breadth_score": float(f.relative_breadth_score),
            "expected_range_12w": float(f.expected_range_12w),
            "expected_range_12m": float(f.expected_range_12m),
            "short_term_movement_intensity": float(f.short_term_movement_intensity),
            "momentum_pulse": float(f.momentum_pulse),
            # v1 accel (needed so feat_dict passed to compute_rocket_score and abstention carries them)
            "rsi_acceleration": float(getattr(f, "rsi_acceleration", 0.0)),
            "volatility_expansion_flag": float(getattr(f, "volatility_expansion_flag", 0.0)),
        })

    ranks = calculate_final_ranks(feature_list, config=scoring_cfg)

    result: dict[str, TickerScore] = {}

    # Resolve as_of once (priority: explicit → cfg → today)
    resolved_as_of = as_of or getattr(cfg, "as_of", None) or _date.today()

    for idx, ticker in enumerate(tickers):
        f = features[ticker]
        feat_dict = feature_list[idx]

        # --- Clean identity resolution ---
        close_val = 0.0
        ticker_as_of = resolved_as_of

        if identity and ticker in identity:
            id_data = identity[ticker]
            close_val = float(id_data.get("close", 0.0))
            if "as_of" in id_data:
                ticker_as_of = id_data["as_of"]
        elif prices and ticker in prices:
            df = prices[ticker]
            if not df.empty and "Close" in df.columns:
                close_val = float(df["Close"].iloc[-1])

        # Scoring signals
        abstention_status = get_abstention_status(feat_dict, config=scoring_cfg)
        rocket_base = compute_rocket_score(feat_dict, config=scoring_cfg)

        # --- News Pulse integration (Phase 3 architect design) ---
        # Compute after base Rocket components, then apply
        news = compute_news_pulse(ticker, ticker_as_of, cfg)
        final_rocket = apply_news_pulse(rocket_base, news, scoring_cfg)

        # Conservative notes (architectural decision) + NewsPulse diagnostic
        notes_parts = [f"Abstention: {abstention_status}"]
        if final_rocket is not None:
            direction = "bullish" if final_rocket > 0 else "bearish" if final_rocket < 0 else "neutral"
            notes_parts.append(f"Rocket: {final_rocket:+.1f} ({direction})")

        # Always include compact NewsPulse diagnostic
        notes_parts.append(f"NewsPulse: {news.encoded} → {news.impact_pct:.1f}% impact")

        # Surface new v1 acceleration features in notes for diagnostics / transparency
        # (values are also stored directly on the TickerScore object)
        rsi_a = float(getattr(f, "rsi_acceleration", feat_dict.get("rsi_acceleration", 0.0)))
        vol_f = float(getattr(f, "volatility_expansion_flag", feat_dict.get("volatility_expansion_flag", 0.0)))
        notes_parts.append(f"AccelRSI: {rsi_a:+.2f} VolExp: {vol_f:.0f}")

        notes = " | ".join(notes_parts)

        score = TickerScore(
            ticker=ticker,
            as_of=ticker_as_of,
            close=close_val,
            rsi=float(f.rsi),
            atr_pct=float(f.atr_pct),
            adx=float(f.adx),
            rs_vs_spy=float(f.rs_vs_spy),
            relative_breadth_score=float(f.relative_breadth_score),
            raw_expected_range_12w=float(f.expected_range_12w),
            raw_expected_range_12m=float(f.expected_range_12m),
            short_term_movement_intensity=float(f.short_term_movement_intensity),
            momentum_pulse=float(f.momentum_pulse),
            # Acceleration v1 (now wired into Rocket; surfaced for diagnostics)
            rsi_acceleration=float(getattr(f, "rsi_acceleration", 0.0)),
            volatility_expansion_flag=float(getattr(f, "volatility_expansion_flag", 0.0)),
            # Phase 3 results
            final_rank=ranks[idx] if idx < len(ranks) else None,
            bandits_rocket=final_rocket,
            notes=notes,
            # Catalyst for override logic (if provided by caller; enables live-run override)
            catalyst_strength_score=(catalysts or {}).get(ticker),
        )

        result[ticker] = score

    return result


# =============================================================================
# Small Reusable Helper (recommended for ergonomic usage)
# =============================================================================

def build_identity_from_prices(
    prices: dict[str, pd.DataFrame],
    as_of: date | None = None,
) -> dict[str, dict[str, Any]]:
    """Convert raw price DataFrames into the lightweight `identity` dict
    format expected by `scoring_step()`.

    This is a small convenience helper so callers don't have to manually
    extract the latest close for every ticker.

    Args:
        prices: Mapping of ticker -> OHLCV DataFrame (must contain a 'Close' column).
        as_of:  Optional date to attach to every ticker's identity entry.
                If omitted, the caller can still pass `as_of` separately to
                `scoring_step()`.

    Returns:
        dict[str, dict[str, Any]] suitable for the `identity=` parameter of
        `scoring_step()`.

    Example:
        identity = build_identity_from_prices(prices, as_of=today)
        scored = scoring_step(features, cfg, identity=identity)
    """
    identity: dict[str, dict[str, Any]] = {}

    for ticker, df in prices.items():
        if df is None or df.empty or "Close" not in df.columns:
            continue

        entry: dict[str, Any] = {
            "close": float(df["Close"].iloc[-1]),
        }
        if as_of is not None:
            entry["as_of"] = as_of

        identity[ticker] = entry

    return identity
