"""
RSI (Relative Strength Index) feature calculation.

Pure function for computing the latest RSI value from price data.
"""

from __future__ import annotations

import pandas as pd


def _compute_rsi_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Internal helper that returns the full RSI time series.

    This is used by the public `rsi()` function and by the feature orchestrator
    when it needs the series (e.g. for momentum slope calculation).
    """
    close = df["Close"].astype(float)
    delta = close.diff()

    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series


def rsi(df: pd.DataFrame, period: int = 14) -> float:
    """
    Compute the latest Wilder RSI value.

    Args:
        df: Price DataFrame with a 'Close' column (DatetimeIndex recommended).
        period: Lookback period for RSI calculation (default 14).

    Returns:
        Latest RSI value as float in range [0, 100].
        Returns 50.0 if insufficient data.

    Notes:
        - Uses standard Wilder exponential smoothing (alpha = 1/period).
        - This is a pure function with no side effects or I/O.
    """
    if "Close" not in df.columns or len(df) < period + 1:
        return 50.0

    rsi_series = _compute_rsi_series(df, period=period)
    latest = rsi_series.iloc[-1]

    if pd.isna(latest):
        return 50.0
    return float(round(latest, 2))


def rsi_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute the full RSI time series.

    This is primarily intended for use by the feature orchestrator
    (compute_features) when it needs the intermediate series for dependent
    calculations such as momentum slope.

    Args:
        df: Price DataFrame with a 'Close' column.
        period: Lookback period for RSI calculation (default 14).

    Returns:
        pandas Series containing the RSI values (same index as input df).
        Returns an empty Series if insufficient data.
    """
    if "Close" not in df.columns or len(df) < period + 1:
        return pd.Series(dtype=float, index=df.index if hasattr(df, 'index') else None)

    series = _compute_rsi_series(df, period=period)
    return series.round(2)
