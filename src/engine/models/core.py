"""
Core engine data models (v2.3).

Contains TickerScore, EngineOutput, RegimeState, EngineConfig,
OutlierEvent, and supporting structures used by the ingestion and feature layers.

These models define the internal engine schema and enforce strict validation
for all downstream scoring, postprocessing, and export steps.

OutlierEvent is a lightweight diagnostic for capturing large realized moves
that were not well explained by the engine's features / scoring (Phase 4+ foundation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Dict, List, Any

# Avoid hard circular import at runtime; use string annotation + lazy default
# from engine.pipeline.steps.scoring.scoring_config import ScoringConfig


@dataclass
class EngineConfig:
    """
    Lightweight runtime configuration for a Bandit's Advantage engine run (Phase 3+).

    Supports two operating modes via the universe fields:
    - Ad-hoc mode: provide `tickers` directly for quick targeted runs.
    - Scheduled / full-run mode: load from `core_universe_path` + optional
      dynamic expansion using `use_dynamic_expansion` + top-N settings.

    data_source controls price history:
      "synthetic" (default), "real"/"csv_dir", "polygon" (fetch+cache with batching/retries), "polygon_cache" (cache only).
    """
    data_source: str = "synthetic"          # "synthetic" | "real" | "csv_dir" | "polygon" | "polygon_cache" | "parquet" | "dataframe"
    # "polygon": live fetch (cache-first) + persist to data/raw/prices
    # "polygon_cache": strict read from cache only (no API) - errors on missing files
    data_path: Optional[str] = None
    ticker_universe: Optional[List[str]] = None
    # Ad-hoc mode: explicit list of tickers (bypasses core + dynamic expansion)
    tickers: Optional[List[str]] = None

    # === Universe management (two-mode design: ad-hoc vs scheduled full run) ===
    use_dynamic_expansion: bool = False
    core_universe_path: Optional[str] = None  # Path to core tickers list (CSV or TXT)
    dynamic_top_stocks: int = 100
    dynamic_top_etfs: int = 200   # 2025-04: increased from 20 for broader ETF coverage in default/scheduled dynamic expansion (see universe.py)

    # ------------------------------------------------------------
    # News / NewsPulse Configuration (lightweight for now)
    # ------------------------------------------------------------
    news_provider: str = "massive"   # Future: "massive", "polygon", etc.

    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    rs_window: int = 63                     # ~3 months trading days
    expected_range_factor: float = 1.5
    synthetic_seed: int = 42
    synthetic_days: int = 400
    as_of: Optional[date] = None

    # === Polygon price ingestion stability (Phase 5.1) ===
    # Controls for batching and retries in fetch_polygon_ohlcv (used when data_source="polygon")
    polygon_batch_size: int = 15
    """Number of tickers to fetch in each batch before pausing (rate limit friendliness)."""
    polygon_batch_pause_seconds: float = 2.0
    """Sleep time between batches during Polygon historical fetches."""
    polygon_max_retries: int = 4
    """Max attempts per ticker before skipping it (with exponential backoff + jitter)."""

    # === Phase 3+: Nested scoring configuration ===
    # This centralizes all abstention thresholds, rocket weights, and
    # final-rank weights. The scoring layer reads directly from cfg.scoring.
    scoring: "ScoringConfig" = field(default_factory=lambda: _default_scoring_config())


@dataclass
class TickerScore:
    """
    Primary per-ticker scoring record (v2.3 physical contract + Phase 2 features).

    Holds identity + the core technical features required for Bandit's Rocket
    and final_rank calculations (the rocket and rank themselves are populated
    in later phases).

    Fields are intentionally kept close to the v2 analysis workbook columns
    so that Scorecard.xlsx export and history archiving remain compatible.

    Phase 3+ additions:
    - bandits_rocket / final_rank
    - realized_* + range_status_* fields for lightweight realized-vs-expected
      diagnostics (populated via compare_realized_to_expected when data is supplied).
    """

    # Identity
    ticker: str
    as_of: date
    close: float

    # === Phase 2 core technical features (user-specified) ===
    rsi: float
    atr_pct: float                  # ATR as percentage of close
    adx: float
    rs_vs_spy: float                # Relative strength vs SPY (or benchmark)
    relative_breadth_score: float   # Cross-sectional breadth participation
    raw_expected_range_12w: float
    raw_expected_range_12m: float
    short_term_movement_intensity: float
    momentum_pulse: float

    # === Acceleration / Transition Features (v1 foundation) ===
    # Simple delta and regime signals computed in the feature layer.
    # Intended for future use inside compute_rocket_score or behavioral rules.
    # Safe defaults for backward compatibility with older feature dicts.
    rsi_acceleration: Optional[float] = 0.0
    volatility_expansion_flag: Optional[float] = 0.0
    # v5: RS Acceleration (slope of relative strength) for transitional improvement detection
    rs_acceleration: Optional[float] = 0.0  # feat_rs_acceleration / feat_rs_acceleration in snapshots

    # Catalyst strength (v2.2) — populated by replay full_export and future news integration.
    # Used by conditional Catalyst Override logic (_should_apply_catalyst_override) to
    # downgrade severity of high_atr_pct / high_stm factors when alpha + catalyst align.
    catalyst_strength_score: Optional[float] = None

    # === Additional fields observed in v2.3 output (populated progressively) ===
    p_base_12w: Optional[float] = None
    vol_momentum_12w: Optional[float] = None
    strength_numeric: Optional[float] = None
    roadmap_score: Optional[float] = None

    # Regime / qualitative (Phase 2 can leave many as None)
    quality: Optional[str] = None
    risk_state: Optional[str] = None
    confidence_bucket: Optional[str] = None
    directional_bias: Optional[str] = None

    # Final scoring (Phase 3+)
    bandits_rocket: Optional[float] = None
    final_rank: Optional[int] = None

    # === Phase 3+ lightweight realized vs expected range diagnostics ===
    # Populated only when the caller supplies realized returns (e.g. from a
    # subsequent data pull, portfolio history, or forward-looking test).
    # These fields are purely diagnostic at present — no full backtesting
    # or historical tracking engine is implemented yet.
    realized_12w_return: Optional[float] = None
    realized_12m_return: Optional[float] = None
    range_status_12w: Optional[str] = None   # "In Range" | "Exceeding" | "Underperforming" | "No Realized Data"
    range_status_12m: Optional[str] = None

    # Free-form notes / diagnostics
    notes: str = ""

    # Exposure Scaling (v3): graduated position size 0.0 / 0.25 / 0.5 / 1.0
    # Computed in postprocess after Catalyst Override + global cap.
    # Exposed as top-level column in full_export=True CSVs.
    exposure_scale: Optional[float] = None


@dataclass
class EngineOutput:
    """Container for a complete engine run result (Phase 2+)."""
    run_id: str
    as_of: date
    scores: List[TickerScore] = field(default_factory=list)           # Raw scored TickerScore objects (for compatibility)
    scorecard_rows: List["ScorecardRow"] = field(default_factory=list)  # Processed export-ready rows (Phase 3+)
    spy_stats: Dict[str, float] = field(default_factory=dict)
    regime_state: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_score(self, ticker: str) -> Optional[TickerScore]:
        for s in self.scores:
            if s.ticker.upper() == ticker.upper():
                return s
        return None


# Helper to avoid circular import at module load time for default_factory
def _default_scoring_config():
    from engine.pipeline.steps.scoring.scoring_config import ScoringConfig
    return ScoringConfig()


@dataclass
class RegimeState:
    """High-level market regime classification (future expansion)."""
    name: str
    confidence: float
    description: str = ""


@dataclass
class OutlierEvent:
    """
    Lightweight diagnostic record for "unexplained" large moves.

    Captures cases where the realized move significantly exceeded (or fell short of)
    the engine's expected range, even when pre-event features, acceleration signals,
    and news did not strongly support a large move.

    Intended for:
    - Post-run analysis and calibration
    - Building a dataset of "surprises" for future model improvements
    - Manual review / alerting on outliers

    v2 additions: lightweight `regime` tag (e.g. "Trending", "High_Vol") populated
    opportunistically in build_outlier_event from pre-event signals.

    This is intentionally simple (no behavior, just data) so it can be easily
    serialized to JSON/Parquet/CSV or stored in the HistoryArchive.
    """

    ticker: str
    as_of: date

    # Expected vs realized (typically based on 12w expected range)
    expected_move: float          # e.g. raw_expected_range_12w (percentage points)
    realized_move: float
    delta: float                  # realized_move - expected_move  (positive = bigger than expected)

    # Snapshot of the engine state just before the move
    pre_event_features: Dict[str, Any]   # e.g. {"rsi": 55.2, "momentum_pulse": 1.8, ...}

    # Key signals that *were* present (populated opportunistically)
    rsi_acceleration: Optional[float] = None
    volatility_expansion_flag: Optional[float] = None
    news_encoded: Optional[str] = None

    # v2 regime context at time of event (lightweight tagging)
    regime: str = "Unknown"  # "Trending" | "Choppy" | "High_Vol" | "Low_Vol" | "Unknown"

    notes: str = ""   # Free-form: "gap up on earnings", "sector rotation", "false signal", etc.

    # === v1.0 Corporate Actions integration (protective/contextual, not scoring driver) ===
    # Used for ex-div sanity suppression, dividend_cut attribution, recent_split notes.
    # See build_corporate_action_context and sanity logic in expected_range.build_outlier_event.
    corporate_action_context: Optional[dict] = None
    dividend_cut: Optional[dict] = None  # e.g. {"date": "YYYY-MM-DD", "pct": -0.18} for attribution


# Convenience type aliases for Phase 2 (pandas types are used at runtime in readers/features)
PriceDict = Dict[str, Any]
FeatureDict = Dict[str, float]
