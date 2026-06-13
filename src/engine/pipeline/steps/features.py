"""
Features computation pipeline step (Phase 2).

Thin wrapper around engine.features that turns raw price data into
a list of populated TickerScore objects.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.features import compute_features_for_universe, build_ticker_scores
from engine.models.core import TickerScore, EngineConfig


def compute_features(ingest_output: Dict[str, Any], config: EngineConfig | None = None) -> List[TickerScore]:
    """
    Phase 2 feature step.

    Takes the output of the ingest step and returns real TickerScore instances
    with all Phase 2 technical features calculated.
    """
    cfg = config or ingest_output.get("config")
    prices = ingest_output["prices"]
    spy = ingest_output.get("spy")

    raw_features = compute_features_for_universe(prices, spy_df=spy, config=cfg)

    scores = build_ticker_scores(
        raw_features,
        prices=prices,
        as_of=ingest_output.get("as_of"),
        config=cfg,
    )
    return scores
