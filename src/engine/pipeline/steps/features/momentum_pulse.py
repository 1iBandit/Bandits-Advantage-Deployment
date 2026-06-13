"""
Momentum Pulse feature calculation.

Pure function for computing a composite short-term momentum signal.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def momentum_pulse(
    df: pd.DataFrame,
    rsi_series: pd.Series | None = None,
    window: int = 10,
) -> float:
    """
    Compute Momentum Pulse — a composite signal combining RSI slope and price momentum.

    Args:
        df: Price DataFrame with 'Close' column.
        rsi_series: Optional pre-computed RSI series. If not provided, a simple
                    momentum proxy is used.
        window: Lookback for slope and momentum calculations (default 10).

    Returns:
        Momentum Pulse value as float (positive = bullish acceleration).
        Returns 0.0 if data is insufficient.

    Notes:
        - Designed as a leading component for higher-level scoring.
        - Pure function.
    """
    if "Close" not in df.columns or len(df) < window + 5:
        return 0.0

    close = df["Close"].astype(float)

    # Price momentum (simple rate of change)
    price_mom = (close.iloc[-1] / close.iloc[-window - 1] - 1) * 100

    if rsi_series is not None and len(rsi_series) > window:
        rsi_slope = rsi_series.diff(window).iloc[-5:].mean()
    else:
        # Fallback: use rate of change of a short moving average
        sma = close.rolling(5).mean()
        rsi_slope = (sma.iloc[-1] / sma.iloc[-window - 1] - 1) * 50  # scaled proxy

    pulse = (rsi_slope * 0.6) + (price_mom * 0.4)
    return float(round(pulse, 3))
