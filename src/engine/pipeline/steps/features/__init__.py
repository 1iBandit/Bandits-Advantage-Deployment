"""
Feature calculation subpackage for Bandit's Advantage v3.

This package contains pure, testable functions for computing technical features
used in the TickerScore model.

Primary entry point:
    from engine.pipeline.steps.features import compute_features

    features = compute_features(ticker_df, spy_df=spy_df, universe_dfs=universe)

Individual modules are also importable for fine-grained testing:
    from engine.pipeline.steps.features.rsi import rsi
    from engine.pipeline.steps.features.atr import atr_pct
    ...
"""

from .compute_features import (
    TickerFeatures,
    compute_features,
    compute_features_to_dict,
)

__all__ = [
    "TickerFeatures",
    "compute_features",
    "compute_features_to_dict",
]
