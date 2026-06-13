"""
Bandit's Rocket v3.1 - Expected Short-Term Movement Intensity Score

This module computes the core "Bandit's Rocket" score for a ticker.

Design goals (v3.1):
- Symmetrical output scale: -10 to +10
- The absolute value represents expected short-term movement intensity (magnitude)
- The sign represents the expected directional bias of that intensity
- Higher |score| = stronger expected move (in either direction)

Component Weights (v3.1 + v1 accel extensions):
- Short-Term Movement Intensity: 0.35
- Momentum Pulse: 0.35
- Relative Breadth Pulse: 0.25
- News Pulse: 0.05 (wired via news_pulse() stub — currently always 0.0)
- RSI Acceleration (new v1 behavioral): 0.10
- Volatility Expansion Flag (new v1 behavioral): 0.08

Special rule inside Short-Term Movement Intensity:
- Volume is given approximately 25% more influence than pure price movement.

The new acceleration weights are deliberately small and conservative for v1 so
existing Rocket scale/behavior remains stable when the signals are near zero
or modest. They are intended as "behavioral nudges" (trend continuation via
rising RSI, and expected move size via vol expansion).

The function is pure and accepts either a TickerFeatures dataclass
or a plain dictionary with the same keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union, Optional

import numpy as np

from .scoring_config import ScoringConfig, DEFAULT_SCORING_CONFIG
from .news_pulse import news_pulse


# Type alias for flexibility
FeatureInput = Union["TickerFeatures", dict[str, Any]]


@dataclass
class TickerFeatures:
    """Minimal local definition for type safety when the canonical one is not imported."""
    short_term_movement_intensity: float
    momentum_pulse: float
    relative_breadth_score: float
    # Acceleration v1 signals (for compute_rocket_score)
    rsi_acceleration: float = 0.0
    volatility_expansion_flag: float = 0.0


def _get_value(features: FeatureInput, key: str, default: float = 0.0) -> float:
    """Safely extract a feature value from either a dataclass or dict."""
    if isinstance(features, dict):
        return float(features.get(key, default))
    return float(getattr(features, key, default))


def _normalize(value: float, low: float, high: float, symmetric: bool = False) -> float:
    """
    Normalize a value into [0, 1] or [-1, 1] range.

    Args:
        symmetric: If True, output is in [-1, 1] centered at 0.
    """
    if high == low:
        return 0.0

    norm = (value - low) / (high - low)
    norm = max(0.0, min(1.0, norm))

    if symmetric:
        return norm * 2 - 1
    return norm


def compute_rocket_score(
    features: FeatureInput,
    config: Optional[ScoringConfig] = None,
) -> float:
    """
    Compute Bandit's Rocket v3.1 score for a single ticker.

    Args:
        features: Either a TickerFeatures instance or a dictionary containing
                  at minimum the keys:
                    - short_term_movement_intensity
                    - momentum_pulse
                    - relative_breadth_score
                  Optional new v1 keys (gracefully default to 0):
                    - rsi_acceleration
                    - volatility_expansion_flag
        config: Optional ScoringConfig to supply weights and normalization bounds.

    Notes:
        The News Pulse component is obtained by calling news_pulse(features, config).
        It is currently a no-op stub returning 0.0. When a real implementation
        is added to news_pulse.py, it will automatically participate in the
        5% weighted term with no changes required here.

        New v1 acceleration signals (rsi_acceleration, volatility_expansion_flag)
        are incorporated with small dedicated weights from config. They act as
        behavioral nudges without changing the core three components or scale.

    Returns:
        float: Bandit's Rocket score in the range [-10.0, +10.0].
               - The absolute value indicates expected movement intensity.
               - The sign indicates directional bias (positive = bullish bias).
    """
    cfg = config or DEFAULT_SCORING_CONFIG

    # === Extract raw features ===
    stm = _get_value(features, "short_term_movement_intensity", 20.0)
    momentum = _get_value(features, "momentum_pulse", 0.0)
    breadth = _get_value(features, "relative_breadth_score", 50.0)

    # v1 acceleration / behavioral features (new, small impact, defaults safe)
    rsi_accel = _get_value(features, "rsi_acceleration", 0.0)
    vol_exp = _get_value(features, "volatility_expansion_flag", 0.0)

    # ============================================================
    # 1. Short-Term Movement Intensity Component
    # ============================================================
    price_intensity = _normalize(stm, low=cfg.rocket_stm_low, high=cfg.rocket_stm_high)

    # Volume emphasis (25% more influence than price)
    volume_intensity = price_intensity * cfg.rocket_volume_emphasis
    total_weight = 1.0 + cfg.rocket_volume_emphasis
    stm_intensity = (price_intensity * 1.0 + volume_intensity) / total_weight

    # ============================================================
    # 2. Momentum Pulse Component
    # ============================================================
    momentum_intensity = _normalize(
        momentum,
        low=cfg.rocket_momentum_low,
        high=cfg.rocket_momentum_high,
        symmetric=True,
    )

    # ============================================================
    # 3. Relative Breadth Pulse Component
    # ============================================================
    breadth_pulse = _normalize(breadth, low=0.0, high=100.0, symmetric=True)

    # ============================================================
    # 4. RSI Acceleration Component (v1 behavioral signal)
    # ============================================================
    # Positive = rising RSI (improving momentum), contributes to directional bias.
    # Normalized symmetrically like momentum_pulse. Small weight keeps impact conservative.
    rsi_accel_intensity = _normalize(
        rsi_accel,
        low=cfg.rocket_rsi_accel_low,
        high=cfg.rocket_rsi_accel_high,
        symmetric=True,
    )

    # ============================================================
    # 5. Volatility Expansion Flag Component (v1 behavioral signal)
    # ============================================================
    # 0.0 or 1.0 flag. When 1, indicates ATR% is expanding vs recent median
    # (suggests larger expected moves). Applied with momentum sign for direction.
    # Small dedicated weight for v1.
    vol_intensity = float(vol_exp)  # 0 or 1

    # ============================================================
    # 6. News Pulse Component (via dedicated stub)
    # ============================================================
    # Currently returns 0.0 (explicit placeholder).
    # See news_pulse.py for full documentation of the stub and
    # intended future expansion directions.
    # (Note: component numbering updated for v1 accel additions above.)
    news_pulse_val = news_pulse(features, cfg)

    # ============================================================
    # Combine components using config weights
    # ============================================================
    # Note: new accel terms use their own small weights (see ScoringConfig).
    # vol uses momentum sign so expansion boosts expected move in the prevailing direction.
    raw_score = (
        cfg.rocket_stm_weight * stm_intensity * np.sign(momentum_intensity) if momentum_intensity != 0 else 0.0
        + cfg.rocket_momentum_weight * momentum_intensity
        + cfg.rocket_breadth_weight * breadth_pulse
        + cfg.rocket_news_weight * news_pulse_val
        + cfg.rocket_rsi_accel_weight * rsi_accel_intensity
        + cfg.rocket_vol_exp_weight * vol_intensity * (np.sign(momentum_intensity) if momentum_intensity != 0 else 1.0)
    )

    # ============================================================
    # Scale and clip using config multiplier
    # ============================================================
    rocket_score = raw_score * cfg.rocket_scale_multiplier
    rocket_score = max(-10.0, min(10.0, rocket_score))

    return round(float(rocket_score), 2)
