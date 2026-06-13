"""
ScorecardRow model (Phase 3 v1).

Defines the export-oriented row format used by the Scorecard and History Archive.

Design principles for v1 (conservative):
- Promote only the highest-value Phase 3 fields to dedicated columns.
- Keep rich diagnostics (NewsPulse, detailed Rocket commentary, etc.) inside the `notes` field.
- Maintain reasonable compatibility with prior v2-style exports.

New columns in v1:
- final_rank
- bandits_rocket
- abstention_status (parsed)
- rocket_zone (simple ternary: Positive / Neutral / Negative)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class ScorecardRow:
    """
    Flattened, export-friendly representation of a scored ticker.

    This is the primary shape handed to the Excel writer and history archiver.

    === v1 Output Contract (stable columns) ===
    The fields below represent the current agreed-upon columns for Scorecard.xlsx
    and the History Archive in Phase 3 v1.

    Identity + Core Features (largely inherited from v2 workbook for compatibility):
        ticker, as_of, close, rsi, atr_pct, adx, rs_vs_spy, relative_breadth_score,
        momentum_pulse, raw_expected_range_12w, raw_expected_range_12m,
        short_term_movement_intensity

    Phase 3+ Scoring Outputs (modest, high-value additions):
        final_rank, bandits_rocket, abstention_status, rocket_zone

    Layer 1 Abstention Reasoning (added to explain *why* a given abstention_status
    was chosen; captures all contributing factors, risk-ordered):
        abstention_risk     — "Low" | "Medium" | "High"  (overall classification)
        abstention_reason   — Human string, e.g. "momentum_pulse_below_threshold (0.92) + low_relative_breadth (28.4)"
        abstention_details  — list[dict] machine-readable for backtesting/analysis (in to_dict only)

    Diagnostics:
        notes  — Contains the full diagnostic string including Abstention,
                 Rocket commentary, and NewsPulse details. Rich content lives
                 here for v1 to keep the column count manageable.
        corporate_action_context — v1.0 unified CA object (splits, cuts, ex-div, impact, notes list). Contextual/protective.

    This contract should only change with deliberate review. New fields should
    generally be added conservatively.
    """

    # Identity
    ticker: str
    as_of: date
    close: float

    # === Phase 2 core technical features (v1 scorecard columns) ===
    rsi: float
    atr_pct: float
    adx: float
    rs_vs_spy: float
    relative_breadth_score: float
    momentum_pulse: float
    raw_expected_range_12w: float
    raw_expected_range_12m: float
    short_term_movement_intensity: float

    # === Phase 3+ Scoring Outputs (modest set for v1) ===
    final_rank: Optional[int] = None
    bandits_rocket: Optional[float] = None
    abstention_status: Optional[str] = None   # "Trade Eligible" | "Minimal Direction" | "Observe / No Trade"
    rocket_zone: Optional[str] = None         # "Positive" | "Neutral" | "Negative"

    # === Layer 1 Abstention Reasoning (v1) ===
    # Populated for all rows (reason + details empty when "Trade Eligible").
    # Factors are collected from feature values vs ScoringConfig thresholds,
    # ordered by risk (highest first), with overall classification.
    abstention_risk: Optional[str] = None         # "Low" | "Medium" | "High"
    abstention_reason: Optional[str] = None       # e.g. "momentum_pulse_below_threshold (9.37) + low_relative_breadth (0.58)"
    abstention_details: list[dict] = field(default_factory=list)  # structured for analysis / backtesting

    # Diagnostics (rich content stays here for v1)
    notes: str = ""

    # === v1.0 Corporate Actions Context (unified protective/contextual object) ===
    # Built from live corporate_actions module. Not a primary scoring driver.
    # See corporate_action_context spec for full fields (has_recent_split, impact_score, notes list, etc.).
    corporate_action_context: Optional[dict] = None

    # Exposure Scaling (v3): 0.0 / 0.25 / 0.5 / 1.0
    # Added per Exposure Scaling Briefing v3. Stored on row for export/CSV.
    exposure_scale: Optional[float] = None

    @classmethod
    def from_ticker_score(
        cls,
        score: "TickerScore",
        abstention_status: Optional[str] = None,
        rocket_zone: Optional[str] = None,
        abstention_risk: Optional[str] = None,
        abstention_reason: Optional[str] = None,
        abstention_details: Optional[list[dict]] = None,
        corporate_action_context: Optional[dict] = None,
        exposure_scale: Optional[float] = None,
    ) -> "ScorecardRow":
        """
        Factory method to create a ScorecardRow from a TickerScore.

        This centralizes the mapping logic and makes the transformation
        between internal and export models explicit and easy to review.
        Abstention reasoning fields (Layer 1) are passed through from postprocess.
        exposure_scale added per Exposure Scaling Briefing v3.
        """
        return cls(
            ticker=score.ticker,
            as_of=score.as_of,
            close=score.close,
            rsi=score.rsi,
            atr_pct=score.atr_pct,
            adx=score.adx,
            rs_vs_spy=score.rs_vs_spy,
            relative_breadth_score=score.relative_breadth_score,
            momentum_pulse=score.momentum_pulse,
            raw_expected_range_12w=score.raw_expected_range_12w,
            raw_expected_range_12m=score.raw_expected_range_12m,
            short_term_movement_intensity=score.short_term_movement_intensity,
            final_rank=score.final_rank,
            bandits_rocket=score.bandits_rocket,
            abstention_status=abstention_status,
            rocket_zone=rocket_zone,
            abstention_risk=abstention_risk,
            abstention_reason=abstention_reason,
            abstention_details=abstention_details or [],
            notes=score.notes,
            corporate_action_context=corporate_action_context,
            exposure_scale=exposure_scale if exposure_scale is not None else getattr(score, "exposure_scale", None),
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to a flat dictionary suitable for DataFrame / Parquet / CSV export.
        This provides a stable, explicit serialization format for the output contract.
        """
        return {
            "ticker": self.ticker,
            "as_of": self.as_of,
            "close": self.close,
            "rsi": self.rsi,
            "atr_pct": self.atr_pct,
            "adx": self.adx,
            "rs_vs_spy": self.rs_vs_spy,
            "relative_breadth_score": self.relative_breadth_score,
            "momentum_pulse": self.momentum_pulse,
            "raw_expected_range_12w": self.raw_expected_range_12w,
            "raw_expected_range_12m": self.raw_expected_range_12m,
            "short_term_movement_intensity": self.short_term_movement_intensity,
            "final_rank": self.final_rank,
            "bandits_rocket": self.bandits_rocket,
            "abstention_status": self.abstention_status,
            "rocket_zone": self.rocket_zone,
            "abstention_risk": self.abstention_risk,
            "abstention_reason": self.abstention_reason,
            "abstention_details": self.abstention_details,
            "notes": self.notes,
            "corporate_action_context": self.corporate_action_context,
            "exposure_scale": self.exposure_scale,
        }
