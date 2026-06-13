"""
Scoring subpackage for Bandit's Advantage v3 (Phase 3+).

This package provides the main scoring primitives that turn Phase 2
features into trading signals and intensity scores.

Public API (all functions are pure and easy to test):

- `ScoringConfig` dataclass + `DEFAULT_SCORING_CONFIG`
  Central place for all important thresholds and weights.

- `compute_rocket_score(features, config=None)` → Bandit's Rocket v3.1 score (-10 to +10)

- `news_pulse(...)` → News Pulse component (currently always 0.0 — explicit placeholder)

- `calculate_final_ranks(features_list, ..., config=None)` → List of integer ranks

- `get_abstention_status(features, ..., config=None)` → "Trade Eligible" | "Minimal Direction" | "Observe / No Trade"

- `score_ticker(...)` and `apply_scoring(...)` / `scoring_step(...)` (canonical)
  Higher-level helpers. `scoring_step` is the Phase 3 dict-based version.
  Legacy list-based version: `legacy_scoring_step`

- `build_identity_from_prices(prices, as_of=None)`
  Small helper that turns raw price DataFrames into the `identity` dict
  format expected by `scoring_step()`.

- `compare_realized_to_expected(...)` / `compare_realized_ranges(...)` + `RangeComparison`
  Lightweight diagnostic comparison of realized returns vs expected move ranges (12w/12m).

- `build_outlier_event(...)` + `OutlierEvent`
  Builder that returns an OutlierEvent (or None) when realized move greatly exceeds
  the ticker's own expected range (configurable multiplier). Pulls pre-event feature
  snapshot + accel/news signals from the TickerScore. Foundation for surprise analytics.

- `detect_and_build_outliers(scores, realized_returns, threshold_multiplier=2.0)`
  Post-run helper: given a list of TickerScore and a {ticker: realized_move} dict,
  returns all qualifying OutlierEvent instances. Ideal for use after run_engine or
  when you have a batch of results + realized performance data.

- `save_outliers_to_jsonl(events, path)` / `load_outliers_from_jsonl(path)`
  Lightweight JSONL persistence for OutlierEvents (append mode, date-safe, defensive
  on bad lines). Enables accumulating a long-term "surprises" dataset across runs.

Outlier Pipeline (quick start)
------------------------------
After you have TickerScores (e.g. from run_engine or scoring_step) and realized
returns, use:
    outliers = detect_and_build_outliers(scores, realized_returns_dict)
    save_outliers_to_jsonl(outliers, "surprises.jsonl")
See expected_range.py module docstring + its `if __name__ == "__main__":` block
for a complete copy-paste mini workflow and more details.

Example - using ScoringConfig:
    from engine.pipeline.steps.scoring import ScoringConfig, compute_rocket_score

    cfg = ScoringConfig(rocket_stm_weight=0.40, min_momentum_pulse=2.0)
    rocket = compute_rocket_score(my_features, config=cfg)
"""

from .final_rank import calculate_final_ranks
from .abstention import get_abstention_status
from .score_ticker import score_ticker, ScoringResult
from .rocket import compute_rocket_score
from .scoring_step import (
    apply_scoring,
    scoring_step,
    legacy_scoring_step,
    build_identity_from_prices,
)
from .scoring_config import ScoringConfig, DEFAULT_SCORING_CONFIG
from .news_pulse import (
    news_pulse,
    NewsPulseResult,
    compute_news_pulse,
    apply_news_pulse,
)
from .expected_range import (
    compare_realized_to_expected,
    compare_realized_ranges,
    RangeComparison,
    build_outlier_event,
    detect_and_build_outliers,
    save_outliers_to_jsonl,
    load_outliers_from_jsonl,
)

# Re-export core diagnostic model for convenience alongside range comparisons
from engine.models import OutlierEvent

__all__ = [
    "calculate_final_ranks",
    "get_abstention_status",
    "score_ticker",
    "ScoringResult",
    "compute_rocket_score",
    "apply_scoring",
    "scoring_step",
    "legacy_scoring_step",
    "build_identity_from_prices",
    "ScoringConfig",
    "DEFAULT_SCORING_CONFIG",
    # News Pulse
    "news_pulse",
    "NewsPulseResult",
    "compute_news_pulse",
    "apply_news_pulse",
    # Realized vs Expected range diagnostics (lightweight)
    "compare_realized_to_expected",
    "compare_realized_ranges",
    "RangeComparison",
    "build_outlier_event",
    "detect_and_build_outliers",
    "save_outliers_to_jsonl",
    "load_outliers_from_jsonl",
    # Outlier / surprise capture (Phase 4+ foundation)
    "OutlierEvent",
]
