"""
Score Ticker Helper for Bandit's Advantage v3 (Phase 3).

This module provides a convenient bridge between the feature computation layer
and the scoring components. It combines final ranking (when universe context
is available) and abstention logic into a single, easy-to-use function.

Intended usage:
    from engine.pipeline.steps.features.compute_features import TickerFeatures
    from engine.pipeline.steps.scoring.score_ticker import score_ticker

    features = compute_features(ticker_df, spy_df=spy_df)
    result = score_ticker(features, universe=universe_features_list)

    print(result.final_rank)
    print(result.abstention_status)

    # To also include Bandit's Rocket v3.1 score:
    result = score_ticker(features, universe=universe_features_list, include_rocket=True)
    print(result.rocket_score)  # float in [-10, +10] or None
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Sequence, Union, Optional

from .final_rank import calculate_final_ranks
from .abstention import get_abstention_status
from .rocket import compute_rocket_score
from .scoring_config import ScoringConfig

# Use the canonical TickerFeatures when possible
try:
    from engine.pipeline.steps.features.compute_features import TickerFeatures
except ImportError:
    # Fallback local definition for standalone use
    @dataclass
    class TickerFeatures:
        rsi: float
        atr_pct: float
        adx: float
        rs_vs_spy: float
        relative_breadth_score: float
        expected_range_12w: float
        expected_range_12m: float
        short_term_movement_intensity: float
        momentum_pulse: float
        # Acceleration v1 (optional for fallback path)
        rsi_acceleration: float = 0.0
        volatility_expansion_flag: float = 0.0


FeatureLike = Union[TickerFeatures, dict[str, Any]]


@dataclass
class ScoringResult:
    """
    Clean result object returned by score_ticker().

    Fields:
        final_rank: Cross-sectional rank (1 = best) or None
        abstention_status: One of "Trade Eligible", "Minimal Direction", "Observe / No Trade"
        rocket_score: Bandit's Rocket v3.1 score in [-10, +10] (only present when include_rocket=True)
    """
    final_rank: Optional[int]
    abstention_status: str
    rocket_score: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Return the result as a plain dictionary (None fields are included)."""
        return asdict(self)


def score_ticker(
    features: FeatureLike,
    universe: Optional[Sequence[FeatureLike]] = None,
    include_rocket: bool = False,
    config: Optional[ScoringConfig] = None,
) -> ScoringResult:
    """
    Score a single ticker by combining abstention logic and (optionally) final ranking.

    This is the recommended entry point when you have already computed features
    for one or more tickers and want both the rank (if possible) and trade
    eligibility status in one call.

    Args:
        features: The features for the ticker being scored.
                  Can be a TickerFeatures instance or a plain dict with the
                  same keys.
        universe: Optional list of FeatureLike objects representing the full
                  universe of tickers. If provided, final_rank will be computed
                  using calculate_final_ranks(). The rank for *this* ticker is
                  determined by object identity (preferred) or value equality.
        include_rocket: If True, also computes and returns the Bandit's Rocket v3.1
                        score (range -10 to +10). Defaults to False for backward
                        compatibility and to keep the call lightweight when not needed.
        config: Optional ScoringConfig to supply thresholds and weights to the
                underlying scoring functions.

    Returns:
        ScoringResult with:
            - final_rank: int (1 = best) or None if universe was not provided
                          or the ticker could not be located in the universe.
            - abstention_status: str ("Trade Eligible", "Minimal Direction",
                              or "Observe / No Trade")
            - rocket_score: float in [-10, +10] or None (only present when include_rocket=True)

    Notes:
        - This function is pure (no side effects or I/O).
        - When `universe` is provided, ranking is cross-sectional.
        - When `universe` is None, only abstention status is returned.
        - Rocket score computation is optional to keep the helper lightweight.
    """
    # Always compute abstention (works on single ticker)
    abstention_status = get_abstention_status(features, config=config)

    final_rank: Optional[int] = None

    if universe:
        # Compute ranks for the entire universe
        ranks = calculate_final_ranks(universe, config=config)

        # Try to find the position of this ticker's features
        try:
            # Prefer exact object identity
            idx = next(i for i, f in enumerate(universe) if f is features)
        except StopIteration:
            try:
                # Fallback to value equality (works well for dicts and dataclasses)
                idx = next(i for i, f in enumerate(universe) if f == features)
            except StopIteration:
                idx = None

        if idx is not None:
            final_rank = ranks[idx]

    # Optional rocket score (kept separate to avoid unnecessary computation)
    rocket_score: Optional[float] = None
    if include_rocket:
        rocket_score = compute_rocket_score(features, config=config)

    return ScoringResult(
        final_rank=final_rank,
        abstention_status=abstention_status,
        rocket_score=rocket_score,
    )
