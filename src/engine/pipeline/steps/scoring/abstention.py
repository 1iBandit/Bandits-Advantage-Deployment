"""
Abstention logic for Bandit's Advantage v3 (Phase 3).

This module determines whether a ticker should be considered for trading
("Trade Eligible"), shows only minimal directional conviction
("Minimal Direction"), or should be avoided entirely ("Observe / No Trade").

The logic is intentionally transparent and rule-based so it can be
audited and tuned easily.

vNext (per Current State Briefing):
- _should_apply_catalyst_override + _classify_volatility_context helpers
  allow conditional downgrading (not removal) of hard abstention factors
  (high ATR, high STM) when catalyst + momentum + Rocket are strongly aligned
  *and* volatility context is healthy ("expansion_with_trend").
- Goal: risk modulates rather than vetoes aligned trend + catalyst regimes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union, Optional

from .scoring_config import ScoringConfig, DEFAULT_SCORING_CONFIG

FeatureLike = Union["TickerFeatures", dict]


@dataclass
class TickerFeatures:
    """Minimal feature container for type hints."""
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
    if isinstance(obj, dict):
        return float(obj.get(name, default))
    return float(getattr(obj, name, default))


def get_abstention_status(
    features: FeatureLike,
    *,
    config: Optional[ScoringConfig] = None,
    min_momentum_pulse: Optional[float] = None,
    max_atr_pct: Optional[float] = None,
    min_rs_vs_spy: Optional[float] = None,
    min_breadth: Optional[float] = None,
    max_stm: Optional[float] = None,
    min_adx_for_trend: Optional[float] = None,
) -> str:
    """
    Determine the abstention / trade eligibility status for a ticker.

    Args:
        features: Object or dict containing Phase 2 features.
        config: Optional ScoringConfig to supply default thresholds.
        min_momentum_pulse, ... : Individual overrides. If provided, they take
            precedence over values in config (or the built-in defaults).

    Returns:
        One of:
            - "Trade Eligible"
            - "Minimal Direction"
            - "Observe / No Trade"

    Notes:
        - This is a pure function.
        - When a ScoringConfig is passed, its values act as the new defaults.
        - Individual keyword arguments can still be used to override specific values.
    """
    cfg = config or DEFAULT_SCORING_CONFIG

    # Resolve effective thresholds (explicit args override config)
    min_momentum = min_momentum_pulse if min_momentum_pulse is not None else cfg.min_momentum_pulse
    max_atr = max_atr_pct if max_atr_pct is not None else cfg.max_atr_pct
    min_rs = min_rs_vs_spy if min_rs_vs_spy is not None else cfg.min_rs_vs_spy
    min_b = min_breadth if min_breadth is not None else cfg.min_breadth
    max_s = max_stm if max_stm is not None else cfg.max_stm
    min_adx = min_adx_for_trend if min_adx_for_trend is not None else cfg.min_adx_for_trend

    momentum = _get_feature(features, "momentum_pulse")
    atr = _get_feature(features, "atr_pct")
    rs = _get_feature(features, "rs_vs_spy")
    breadth = _get_feature(features, "relative_breadth_score")
    stm = _get_feature(features, "short_term_movement_intensity")
    adx = _get_feature(features, "adx")

    # Strong negative signals → hard abstention
    if (
        momentum < min_momentum * 0.6
        or rs < min_rs * 0.8
        or breadth < min_b * 0.6
        or atr > max_atr * 1.5
    ):
        return "Observe / No Trade"

    # Weak directional conviction
    if (
        momentum < min_momentum
        or adx < min_adx
        or (stm > max_s and atr > max_atr * 0.8)
    ):
        return "Minimal Direction"

    # Positive conditions for trading consideration
    if (
        momentum >= min_momentum
        and rs >= min_rs
        and breadth >= min_b
        and atr <= max_atr
        and stm <= max_s
    ):
        return "Trade Eligible"

    # Default conservative stance
    return "Minimal Direction"


# =============================================================================
# Catalyst Override + Volatility Context helpers (per Current State Briefing)
# These are designed to be called from postprocess._compute_abstention_reasoning
# (and potentially get_abstention_status in the future) to modulate severity
# instead of applying hard vetoes when alpha + catalyst are strongly aligned.
# =============================================================================

def _should_apply_catalyst_override(
    score: "TickerScore", 
    cfg: "ScoringConfig"
) -> bool:
    """
    Conditional override: when catalyst strength + momentum + Rocket are aligned,
    we downgrade (not remove) the severity of volatility and RS-based abstention factors.

    This directly addresses the DOCN-style failure where strong trend expansion
    with catalyst was vetoed purely on elevated ATR.
    """
    cat_strength = getattr(score, "catalyst_strength_score", None)
    if cat_strength is None:
        return False

    momentum = _get_feature(score, "momentum_pulse", 0.0)
    rocket = getattr(score, "bandits_rocket", None) or 0.0
    rs = _get_feature(score, "rs_vs_spy", 0.0)
    rs_impr = getattr(score, "rs_improvement", 0.0) or 0.0

    min_rs = getattr(cfg, "min_rs_vs_spy", 0.85)
    # Allow override even if current rs_vs_spy is below threshold, as long as RS is improving
    rs_ok = (rs >= min_rs) or (rs_impr > 0.01)

    # Also require some basic trend confirmation (close above a simple reference)
    # In replay we don't always have ema20 on the score; caller can pass richer context later.
    # For now we rely primarily on the three signals + positive momentum.
    return (
        cat_strength >= cfg.catalyst_override_threshold
        and momentum >= cfg.momentum_override_threshold
        and rocket > cfg.rocket_override_threshold
        and rs_ok
    )


def _classify_volatility_context(score: "TickerScore") -> str:
    """
    Returns one of:
        'expansion_with_trend'  — high vol that is aligned with strong momentum (good vol)
        'chaotic'               — vol expansion while momentum/acceleration is deteriorating
        'neutral'

    Used to relax high_atr_pct / high_stm penalties only in the healthy case.
    """
    vol_flag = _get_feature(score, "volatility_expansion_flag", 0.0)
    momentum = _get_feature(score, "momentum_pulse", 0.0)
    rsi_accel = _get_feature(score, "rsi_acceleration", 0.0)

    # More robust: require expansion + strong momentum + rsi_accel not deeply negative.
    # For decisive cap on extreme-momentum trend days (e.g. DOCN), very high momentum alone can qualify as healthy context.
    if (vol_flag == 1.0 and momentum > 20 and rsi_accel > -10.0) or momentum > 50:
        return "expansion_with_trend"
    if momentum < -15 or rsi_accel < -10:
        return "chaotic"
    return "neutral"
