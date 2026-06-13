"""
Short-Term Movement Intensity (STM) feature calculation.

Pure function for measuring recent price movement volatility / intensity.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def short_term_movement_intensity(
    df: pd.DataFrame,
    window: int = 20,
) -> float:
    """
    Compute Short-Term Movement Intensity.

    Measures the annualized standard deviation of daily returns over a short window.
    Higher values indicate more violent short-term price action.

    Args:
        df: Price DataFrame with 'Close' column.
        window: Lookback window in trading days (default 20).

    Returns:
        Intensity value as float (annualized volatility percentage).
        Returns 15.0 as neutral default if insufficient data.

    Notes:
        - Pure function.
    """
    if "Close" not in df.columns or len(df) < window + 1:
        return 15.0

    close = df["Close"].astype(float)
    rets = close.pct_change().dropna().tail(window)

    if len(rets) < 5:
        return 15.0

    intensity = rets.std() * np.sqrt(252) * 100
    return float(round(intensity, 2))
