"""
ATR% (Average True Range as percentage of price) feature calculation.

Pure function for computing the latest ATR% value.
"""

from __future__ import annotations

import pandas as pd


def _compute_atr_pct_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Internal helper that returns the full ATR% time series.

    Used by the public `atr_pct()` and by the feature orchestrator.
    """
    required = {"High", "Low", "Close"}
    if not required.issubset(df.columns):
        return pd.Series(dtype=float, index=getattr(df, 'index', None))

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    atr_pct_series = (atr / close) * 100
    return atr_pct_series


def atr_pct(df: pd.DataFrame, period: int = 14) -> float:
    """
    Compute the latest ATR expressed as a percentage of the current close.

    Args:
        df: Price DataFrame with 'High', 'Low', and 'Close' columns.
        period: Lookback period for ATR (default 14).

    Returns:
        Latest ATR% value as float (e.g. 2.35 for 2.35%).
        Returns 0.0 if insufficient data.

    Notes:
        - Uses Wilder smoothing (same as standard ATR implementations).
        - Pure function — no side effects.
    """
    required = {"High", "Low", "Close"}
    if not required.issubset(df.columns) or len(df) < period + 1:
        return 0.0

    series = _compute_atr_pct_series(df, period=period)
    latest_atr_pct = series.iloc[-1]

    if pd.isna(latest_atr_pct):
        return 0.0
    return float(round(latest_atr_pct, 3))


def atr_pct_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute the full ATR% time series.

    Primarily intended for use by the feature orchestrator when it needs
    the intermediate series (e.g. for expected range calculations).

    Args:
        df: Price DataFrame with 'High', 'Low', and 'Close' columns.
        period: Lookback period for ATR (default 14).

    Returns:
        pandas Series containing ATR% values.
    """
    if not {"High", "Low", "Close"}.issubset(df.columns) or len(df) < period + 1:
        return pd.Series(dtype=float, index=getattr(df, 'index', None))

    series = _compute_atr_pct_series(df, period=period)
    return series.round(3)
