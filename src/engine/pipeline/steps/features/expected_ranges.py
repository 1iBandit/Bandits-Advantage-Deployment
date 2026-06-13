"""
Expected Ranges (12w and 12m) feature calculation.

Pure function for computing raw expected price move ranges.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def expected_ranges(
    df: pd.DataFrame,
    atr_pct_series: pd.Series | None = None,
    factor: float = 1.5,
) -> tuple[float, float]:
    """
    Compute raw expected move ranges for 12 weeks and 12 months.

    Args:
        df: Price DataFrame with 'Close' column.
        atr_pct_series: Optional pre-computed ATR% series (if not provided,
                        will be approximated from recent volatility).
        factor: Scaling factor applied to volatility (default 1.5).

    Returns:
        Tuple of (expected_range_12w, expected_range_12m) as percentages.
        Returns (8.0, 22.0) as safe defaults if data is insufficient.

    Notes:
        - Uses a volatility-based approximation (ATR% or realized vol).
        - Pure function.
    """
    if "Close" not in df.columns or len(df) < 30:
        return (8.0, 22.0)

    close = df["Close"].astype(float)

    if atr_pct_series is not None and len(atr_pct_series) >= 20:
        recent_vol = atr_pct_series.tail(20).mean()
    else:
        # Fallback: 20-day realized volatility annualized
        rets = close.pct_change().dropna().tail(20)
        recent_vol = rets.std() * np.sqrt(252) * 100

    if pd.isna(recent_vol) or recent_vol <= 0:
        return (8.0, 22.0)

    # Approximate trading days
    exp_12w = recent_vol * factor * np.sqrt(63 / 252)
    exp_12m = recent_vol * factor * np.sqrt(252 / 252)

    return (round(exp_12w, 1), round(exp_12m, 1))
