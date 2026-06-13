"""
ADX (Average Directional Index) feature calculation.

Pure function for computing the latest ADX value.
"""

from __future__ import annotations

import pandas as pd


def adx(df: pd.DataFrame, period: int = 14) -> float:
    """
    Compute the latest ADX (Average Directional Index) value.

    Args:
        df: Price DataFrame with 'High', 'Low', and 'Close' columns.
        period: Lookback period (default 14).

    Returns:
        Latest ADX value as float in range [0, 100].
        Returns 20.0 (neutral) if insufficient data.

    Notes:
        - Standard implementation using +DI and -DI.
        - Pure function with no side effects.
    """
    required = {"High", "Low", "Close"}
    if not required.issubset(df.columns) or len(df) < period * 2:
        return 20.0

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)

    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di) * 100
    adx_series = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    latest = adx_series.iloc[-1]
    if pd.isna(latest):
        return 20.0
    return float(round(latest, 2))
