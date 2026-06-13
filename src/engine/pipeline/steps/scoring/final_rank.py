"""
Final Rank calculation for Bandit's Advantage v3 (Phase 3).

This module provides a pure function to compute cross-sectional final ranks
for a list of tickers based on their Phase 2 technical features.

The ranking is designed to surface tickers with strong momentum characteristics,
favorable relative strength, and good breadth participation, while applying
modest risk adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Union, Optional

from .scoring_config import ScoringConfig, DEFAULT_SCORING_CONFIG

# We accept either the TickerFeatures dataclass or any object/dict
# that has the required Phase 2 feature attributes.
FeatureLike = Union["TickerFeatures", dict]


@dataclass
class TickerFeatures:
    """Minimal local copy of the expected feature container for type clarity."""
    rsi: float
    atr_pct: float
    adx: float
    rs_vs_spy: float
    relative_breadth_score: float
    expected_range_12w: float
    expected_range_12m: float
    short_term_movement_intensity: float
    momentum_pulse: float


def _get_feature(obj: FeatureLike, name: str, default: float = 0.0) -> float:
    """Helper to extract feature value from dataclass or dict."""
    if isinstance(obj, dict):
        return float(obj.get(name, default))
    return float(getattr(obj, name, default))


def calculate_final_ranks(
    features_list: Sequence[FeatureLike],
    tickers: Optional[Sequence[str]] = None,
    weights: Optional[dict] = None,
    config: Optional[ScoringConfig] = None,
) -> List[int]:
    """
    Calculate final ranks for a list of tickers based on Phase 2 features.

    Higher composite scores receive better (lower) ranks. Rank 1 = best.

    Args:
        features_list: Sequence of objects containing the Phase 2 features.
        tickers: Optional list of ticker symbols (for debugging only).
        weights: Optional custom weights (overrides config).
        config: Optional ScoringConfig whose final_rank_weights will be used
                if `weights` is not provided.

    Returns:
        List of integer ranks (1-based) in the same order.
    """
    if not features_list:
        return []

    cfg = config or DEFAULT_SCORING_CONFIG
    base_weights = cfg.final_rank_weights

    w = {**base_weights, **(weights or {})}

    scores = []
    for feat in features_list:
        score = 0.0
        for name, weight in w.items():
            val = _get_feature(feat, name, 0.0)
            score += weight * val
        scores.append(score)

    # Create (score, original_index) pairs for stable ranking
    indexed_scores = list(enumerate(scores))
    # Sort descending by score (higher better), stable by original index on ties
    sorted_indices = sorted(indexed_scores, key=lambda x: (-x[1], x[0]))

    ranks = [0] * len(features_list)
    for rank, (orig_idx, _) in enumerate(sorted_indices, start=1):
        ranks[orig_idx] = rank

    return ranks
