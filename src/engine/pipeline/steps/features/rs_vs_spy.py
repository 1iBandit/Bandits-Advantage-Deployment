"""
RS vs SPY (Relative Strength vs Benchmark) feature calculation.

Pure function for computing relative strength of a ticker against SPY (or other benchmark).
"""

from __future__ import annotations

import pandas as pd


def rs_vs_spy(
    ticker_df: pd.DataFrame,
    spy_df: pd.DataFrame,
    window: int = 63,
) -> float:
    """
    Compute relative strength of the ticker versus the benchmark (typically SPY).

    Args:
        ticker_df: Price DataFrame for the ticker (must have 'Close').
        spy_df: Price DataFrame for the benchmark (must have 'Close').
        window: Lookback period in trading days (default 63 ≈ 3 months).

    Returns:
        Relative strength as float (positive = outperformed benchmark).
        Returns 0.0 if insufficient data.

    Notes:
        - Calculated as: (ticker_return / spy_return) - 1 over the window.
        - Pure function.
    """
    if "Close" not in ticker_df.columns or "Close" not in spy_df.columns:
        return 0.0

    min_len = min(len(ticker_df), len(spy_df))
    if min_len < window + 1:
        return 0.0

    ticker_close = ticker_df["Close"].astype(float).iloc[-window - 1 :]
    spy_close = spy_df["Close"].astype(float).iloc[-window - 1 :]

    ticker_ret = (ticker_close.iloc[-1] / ticker_close.iloc[0]) - 1
    spy_ret = (spy_close.iloc[-1] / spy_close.iloc[0]) - 1

    if spy_ret == 0:
        return 0.0

    rs = (ticker_ret / spy_ret) - 1
    return float(round(rs, 4))
