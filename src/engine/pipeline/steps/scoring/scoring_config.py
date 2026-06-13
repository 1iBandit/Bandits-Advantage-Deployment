"""
ScoringConfig for Bandit's Advantage v3 (Phase 3+).

This dataclass centralizes the most important tunable parameters used
across the scoring modules. It makes the system easier to configure,
backtest, and tune without touching multiple source files.

This is an initial focused version containing the highest-impact parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ScoringConfig:
    """
    Configuration for the Bandit's Advantage scoring engine.

    All fields have sensible defaults that match the original v3.1 behavior
    before centralized configuration was introduced.

    Sections:
    - Abstention: Thresholds used by get_abstention_status()
    - Rocket: Weights and normalization parameters for compute_rocket_score()
    - Final Rank: Default feature weights for calculate_final_ranks()
    """

    # -------------------------------------------------------------------------
    # Abstention thresholds (used in get_abstention_status)
    # -------------------------------------------------------------------------
    min_momentum_pulse: float = 1.5
    """Minimum momentum_pulse required to be considered for 'Trade Eligible'."""

    max_atr_pct: float = 4.0
    """Maximum acceptable ATR% (volatility filter). Higher values increase risk."""

    min_rs_vs_spy: float = 0.85
    """Minimum relative strength vs benchmark (e.g. SPY)."""

    min_breadth: float = 35.0
    """Minimum relative_breadth_score (0-100 scale)."""

    max_stm: float = 45.0
    """Maximum short_term_movement_intensity (avoids excessive short-term chop)."""

    min_adx_for_trend: float = 18.0
    """Minimum ADX value to consider a ticker as having meaningful direction."""

    # -------------------------------------------------------------------------
    # Catalyst Override thresholds (used for conditional downgrading of abstention)
    # These allow strong alpha + catalyst alignment to soften hard volatility/RS vetoes.
    # See _should_apply_catalyst_override and integration in postprocess.
    # -------------------------------------------------------------------------
    catalyst_override_threshold: float = 0.40
    """Minimum catalyst_strength_score required to consider overriding abstention severity."""
    momentum_override_threshold: float = 25.0
    """Minimum momentum_pulse required (in conjunction with catalyst) for override."""
    rocket_override_threshold: float = 0.0
    """Minimum bandits_rocket (typically > 0) required for override eligibility."""

    # -------------------------------------------------------------------------
    # Exposure Scaling v3 thresholds (used by compute_exposure_scale)
    # These drive the 0% / 25% / 50% / 100% tiers.
    # -------------------------------------------------------------------------
    momentum_full_conviction_threshold: float = 50.0
    """momentum_pulse threshold for 100% exposure (elite alignment)."""
    rocket_full_conviction_threshold: float = 3.0
    """bandits_rocket threshold for 100% exposure (elite alignment)."""

    # -------------------------------------------------------------------------
    # Calibration / hit-rate logging (v4) - optional thresholds for future tuning
    # of diagnostic label generation or filtering.
    # -------------------------------------------------------------------------
    calibration_momentum_full_conviction_threshold: float = 50.0
    """Momentum threshold used in diagnostic labeling for 'high conviction' regimes."""
    calibration_rocket_full_conviction_threshold: float = 3.0
    """Rocket threshold used in diagnostic labeling for 'high conviction' regimes."""

    # -------------------------------------------------------------------------
    # Rocket v3.1 parameters (used in compute_rocket_score)
    # -------------------------------------------------------------------------
    rocket_stm_weight: float = 0.35
    """Weight for the Short-Term Movement Intensity component."""

    rocket_momentum_weight: float = 0.35
    """Weight for the Momentum Pulse component."""

    rocket_breadth_weight: float = 0.25
    """Weight for the Relative Breadth Pulse component."""

    rocket_news_weight: float = 0.05
    """Weight for the News Pulse component (currently a placeholder)."""

    # --- New v1 behavioral / acceleration signals (small conservative weights) ---
    rocket_rsi_accel_weight: float = 0.10
    """Small weight (v1) for RSI acceleration delta component in Rocket score.
    Positive delta (rising RSI) contributes bullish bias to the intensity score.
    Kept small to preserve stability of overall [-10, +10] scale.
    """

    rocket_vol_exp_weight: float = 0.08
    """Small weight (v1) for volatility expansion flag (0/1) in Rocket score.
    When flag=1 (ATR% expanding vs recent median), adds to expected movement
    intensity (signed by momentum direction). Deliberately conservative for v1.
    """

    rocket_stm_low: float = 15.0
    rocket_stm_high: float = 55.0
    """Normalization bounds for short_term_movement_intensity (maps to ~0-1)."""

    rocket_momentum_low: float = -10.0
    rocket_momentum_high: float = 10.0
    """Normalization bounds for momentum_pulse (maps to -1 to +1)."""

    rocket_rsi_accel_low: float = -20.0
    rocket_rsi_accel_high: float = 20.0
    """Normalization bounds for rsi_acceleration (delta RSI, symmetric -1 to +1)."""

    rocket_volume_emphasis: float = 1.25
    """How much more influence volume has vs pure price movement inside STM (1.0 = equal)."""

    rocket_scale_multiplier: float = 11.5
    """Final multiplier applied before clipping to [-10, +10]."""

    # -------------------------------------------------------------------------
    # Final Rank weights (used in calculate_final_ranks)
    # -------------------------------------------------------------------------
    final_rank_weights: Dict[str, float] = field(default_factory=lambda: {
        "momentum_pulse": 0.30,
        "rs_vs_spy": 0.20,
        "relative_breadth_score": 0.20,
        "expected_range_12w": 0.10,
        "expected_range_12m": 0.05,
        "atr_pct": -0.10,                    # Higher volatility is a penalty
        "adx": -0.05,                        # Very strong trends can be risky
        "short_term_movement_intensity": -0.05,  # Excessive short-term chop
        "rsi": 0.0,                          # Neutral (more relevant in abstention)
    })
    """Default feature weights for the composite final rank score.
    Positive weights increase rank, negative weights act as penalties.
    """

    def __post_init__(self):
        # Ensure weights is always a dict (helps with dataclass copy / serialization)
        if self.final_rank_weights is None:
            self.final_rank_weights = {}


# Convenience singleton with the original v3.1 defaults
DEFAULT_SCORING_CONFIG = ScoringConfig()


# Example usage
if __name__ == "__main__":
    # Create a custom configuration
    my_config = ScoringConfig(
        min_momentum_pulse=2.0,
        max_atr_pct=3.5,
        rocket_stm_weight=0.40,
        rocket_momentum_weight=0.30,
    )

    print("Custom ScoringConfig created:")
    print(f"  min_momentum_pulse = {my_config.min_momentum_pulse}")
    print(f"  rocket_stm_weight  = {my_config.rocket_stm_weight}")
    print(f"  final_rank_weights keys = {list(my_config.final_rank_weights.keys())}")
