"""
Feature Orchestrator for Bandit's Advantage v3.

This module provides a single, clean entry point that coordinates the
calculation of all Phase 2 technical features for a given ticker.

It is designed to be:
- Easy to use from the pipeline (ingest → features)
- Easy to test (pure function with clear inputs/outputs)
- Well documented for future maintainers

The orchestrator computes intermediate values (such as RSI series and ATR%)
once and reuses them where beneficial (e.g. passing RSI to momentum_pulse,
ATR% to expected_ranges).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

# Import all individual pure feature functions
from .rsi import rsi, rsi_series
from .atr import atr_pct, atr_pct_series
from .adx import adx
from .rs_vs_spy import rs_vs_spy
from .breadth import relative_breadth_score
from .expected_ranges import expected_ranges
from .stm import short_term_movement_intensity
from .momentum_pulse import momentum_pulse


# =============================================================================
# Acceleration / Transition Features (Phase 4 foundation - lightweight)
# These are simple delta / regime detectors intended to feed future Rocket
# components (e.g. as additional inputs to compute_rocket_score or news gating).
# They are computed here in the orchestrator for efficiency (reuse series).
# =============================================================================

def rsi_acceleration(ticker_df: pd.DataFrame, period: int = 14, lookback: int = 3) -> float:
    """
    Simple 1st-order acceleration in RSI.

    Returns the change in RSI over the lookback window (current - value lookback bars ago).
    Positive = RSI rising (momentum improving), negative = fading.

    Lightweight v1: uses the existing rsi_series helper. Returns 0.0 on insufficient data.
    """
    if "Close" not in ticker_df.columns or len(ticker_df) < period + lookback + 1:
        return 0.0
    try:
        rs = rsi_series(ticker_df, period=period)
        if len(rs) <= lookback:
            return 0.0
        delta = float(rs.iloc[-1] - rs.iloc[-(lookback + 1)])
        return delta
    except Exception:
        return 0.0


def volatility_expansion_flag(ticker_df: pd.DataFrame, period: int = 14, window: int = 20) -> float:
    """
    Binary-ish expansion flag for volatility (ATR%).

    Returns 1.0 if the latest ATR% is above the median of the trailing `window`
    ATR% values (i.e. volatility is expanding relative to recent history).
    Returns 0.0 otherwise.

    This is a very conservative "is vol rising?" signal for later use in
    position sizing, abstention, or rocket adjustments. Not a magnitude.
    """
    if not {"High", "Low", "Close"}.issubset(ticker_df.columns) or len(ticker_df) < period + window:
        return 0.0
    try:
        atrs = atr_pct_series(ticker_df, period=period)
        if len(atrs) < window:
            return 0.0
        recent = atrs.tail(window)
        med = float(recent.median())
        curr = float(atrs.iloc[-1])
        return 1.0 if curr > med else 0.0
    except Exception:
        return 0.0


@dataclass
class TickerFeatures:
    """
    Container for all computed Phase 2 features for a single ticker.

    This dataclass provides a clean, typed structure that can be easily
    converted into a TickerScore (in models/core.py) or used for further
    analysis / scoring.

    Phase 4 additions (acceleration layer):
        rsi_acceleration, volatility_expansion_flag
    """

    rsi: float
    atr_pct: float
    adx: float
    rs_vs_spy: float
    relative_breadth_score: float
    expected_range_12w: float
    expected_range_12m: float
    short_term_movement_intensity: float
    momentum_pulse: float

    # === Acceleration / Transition Features (v1 foundation) ===
    # Computed in the same orchestrator for efficiency. Will be available for
    # future Rocket weighting or behavioral rules.
    rsi_acceleration: float = 0.0          # delta RSI (e.g. 3-period change)
    volatility_expansion_flag: float = 0.0  # 1.0 if current ATR% > recent median ATR% else 0.0
    rs_acceleration: float = 0.0  # v5: slope of RS vs SPY for transitional improvement (feat_rs_acceleration)


def compute_features(
    ticker_df: pd.DataFrame,
    spy_df: pd.DataFrame | None = None,
    universe_dfs: dict[str, pd.DataFrame] | None = None,
    rsi_period: int = 14,
    atr_period: int = 14,
    adx_period: int = 14,
    rs_window: int = 63,
    stm_window: int = 20,
    momentum_window: int = 10,
    expected_range_factor: float = 1.5,
) -> TickerFeatures:
    """
    Compute all Phase 2 technical features for a single ticker.

    This is the main orchestrator function. It coordinates calls to the
    individual feature modules while handling shared computations
    efficiently.

    Args:
        ticker_df: OHLCV DataFrame for the ticker being analyzed.
                   Must contain at minimum 'Close', and preferably
                   'High' and 'Low' for ATR/ADX.
        spy_df: Optional benchmark DataFrame (usually SPY). Required for
                rs_vs_spy. If None, rs_vs_spy will return 0.0.
        universe_dfs: Optional dictionary of {ticker: df} for the full
                      universe. Required for relative_breadth_score.
                      If None, breadth score defaults to 50.0.
        rsi_period: Period for RSI calculation.
        atr_period: Period for ATR calculation.
        adx_period: Period for ADX calculation.
        rs_window: Window for relative strength vs SPY.
        stm_window: Window for short-term movement intensity.
        momentum_window: Window for momentum pulse calculation.
        expected_range_factor: Scaling factor used in expected ranges.

    Returns:
        TickerFeatures dataclass containing all computed feature values.

    Notes:
        - This function is pure (no I/O).
        - It obtains intermediate series (RSI, ATR%) from the dedicated
          series helpers in rsi.py and atr.py (no duplicated calculation logic).
        - All individual feature functions remain independently testable.
    """
    # === Individual feature calculations (scalars) ===
    # We call the public scalar functions for the final feature values.
    # This ensures the core logic always lives in the individual modules.
    rsi_val = rsi(ticker_df, period=rsi_period)
    atr_val = atr_pct(ticker_df, period=atr_period)

    # === Intermediate series (only when needed by dependent features) ===
    # We obtain the full series from the dedicated series helpers in the
    # leaf modules. This eliminates duplication of the RSI / ATR calculation logic.
    rsi_series_val = None
    atr_pct_series_val = None

    # Only compute the RSI series if momentum_pulse can benefit from it
    if "Close" in ticker_df.columns and len(ticker_df) >= rsi_period + 1:
        rsi_series_val = rsi_series(ticker_df, period=rsi_period)

    # Only compute the ATR% series if expected_ranges can benefit from it
    if {"High", "Low", "Close"}.issubset(ticker_df.columns) and len(ticker_df) >= atr_period + 1:
        atr_pct_series_val = atr_pct_series(ticker_df, period=atr_period)

    adx_val = adx(ticker_df, period=adx_period)

    # RS vs SPY (requires spy_df)
    rs_val = rs_vs_spy(ticker_df, spy_df, window=rs_window) if spy_df is not None else 0.0

    # Relative Breadth Score (requires universe_dfs)
    breadth_val = (
        relative_breadth_score(ticker_df, universe_dfs, window=rs_window)
        if universe_dfs is not None
        else 50.0
    )

    # Expected Ranges (reuses atr_pct_series_val if available)
    exp_12w, exp_12m = expected_ranges(
        ticker_df,
        atr_pct_series=atr_pct_series_val,
        factor=expected_range_factor,
    )

    stm_val = short_term_movement_intensity(ticker_df, window=stm_window)

    # Momentum Pulse (reuses rsi_series_val if available)
    pulse_val = momentum_pulse(
        ticker_df,
        rsi_series=rsi_series_val,
        window=momentum_window,
    )

    # === Acceleration features (v1 - lightweight, reuse series where possible) ===
    rsi_accel = rsi_acceleration(ticker_df, period=rsi_period)
    vol_flag = volatility_expansion_flag(ticker_df, period=atr_period)

    # v5: RS Acceleration (slope of RS vs SPY) for transitional state detection (per Briefing v5)
    rs_accel = 0.0
    if spy_df is not None and len(ticker_df) > 10 and len(spy_df) > 10:
        try:
            t_ret = ticker_df["Close"].iloc[-1] / ticker_df["Close"].iloc[-6] - 1 if len(ticker_df) > 5 else 0.0
            s_ret = spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[-6] - 1 if len(spy_df) > 5 else 0.0
            recent_rs = t_ret - s_ret
            t_ret_past = ticker_df["Close"].iloc[-6] / ticker_df["Close"].iloc[-11] - 1 if len(ticker_df) > 10 else recent_rs
            s_ret_past = spy_df["Close"].iloc[-6] / spy_df["Close"].iloc[-11] - 1 if len(spy_df) > 10 else s_ret
            past_rs = t_ret_past - s_ret_past
            if abs(past_rs) > 0.0001:
                rs_accel = round( (recent_rs - past_rs) / abs(past_rs) , 4)
        except Exception:
            rs_accel = 0.0

    # Assemble and return
    return TickerFeatures(
        rsi=rsi_val,
        atr_pct=atr_val,
        adx=adx_val,
        rs_vs_spy=rs_val,
        relative_breadth_score=breadth_val,
        expected_range_12w=exp_12w,
        expected_range_12m=exp_12m,
        short_term_movement_intensity=stm_val,
        momentum_pulse=pulse_val,
        rsi_acceleration=rsi_accel,
        volatility_expansion_flag=vol_flag,
        rs_acceleration=rs_accel,  # v5 feat_rs_acceleration
    )


def compute_features_to_dict(
    ticker_df: pd.DataFrame,
    spy_df: pd.DataFrame | None = None,
    universe_dfs: dict[str, pd.DataFrame] | None = None,
    **kwargs: Any,
) -> dict[str, float]:
    """
    Convenience wrapper that returns features as a plain dictionary.

    Useful when you don't want to import the TickerFeatures dataclass
    or when serializing results.
    """
    features = compute_features(
        ticker_df=ticker_df,
        spy_df=spy_df,
        universe_dfs=universe_dfs,
        **kwargs,
    )
    return {
        "rsi": features.rsi,
        "atr_pct": features.atr_pct,
        "adx": features.adx,
        "rs_vs_spy": features.rs_vs_spy,
        "relative_breadth_score": features.relative_breadth_score,
        "expected_range_12w": features.expected_range_12w,
        "expected_range_12m": features.expected_range_12m,
        "short_term_movement_intensity": features.short_term_movement_intensity,
        "momentum_pulse": features.momentum_pulse,
        "rsi_acceleration": getattr(features, "rsi_acceleration", 0.0),
        "volatility_expansion_flag": getattr(features, "volatility_expansion_flag", 0.0),
        "rs_acceleration": getattr(features, "rs_acceleration", 0.0),  # v5
    }
