"""
Relative_Breadth_Score feature calculation.

Pure function for computing a cross-sectional breadth participation score.
"""

from __future__ import annotations

import pandas as pd


def relative_breadth_score(
    ticker_df: pd.DataFrame,
    universe_dfs: dict[str, pd.DataFrame],
    window: int = 63,
) -> float:
    """
    Compute the ticker's relative breadth score within a universe.

    Args:
        ticker_df: Price DataFrame for the target ticker.
        universe_dfs: Dictionary of {ticker: price_df} for the full universe
                      (should include the target ticker).
        window: Lookback period for momentum calculation (default 63).

    Returns:
        Breadth score as float in [0, 100], representing the percentile rank
        of the ticker's recent performance within the universe.
        Returns 50.0 if data is insufficient.

    Notes:
        - Uses simple return over the window for ranking.
        - Pure function — no I/O.
    """
    if "Close" not in ticker_df.columns or len(universe_dfs) < 3:
        return 50.0

    returns: dict[str, float] = {}

    for t, df in universe_dfs.items():
        if "Close" not in df.columns or len(df) < window + 1:
            continue
        close = df["Close"].astype(float)
        ret = (close.iloc[-1] / close.iloc[-window - 1]) - 1
        if pd.notna(ret):
            returns[t] = ret

    if not returns or len(returns) < 3:
        return 50.0

    target_ticker = None
    # Try to identify target by matching the last close value (simple heuristic)
    target_close = ticker_df["Close"].iloc[-1]
    for t, df in universe_dfs.items():
        if abs(df["Close"].iloc[-1] - target_close) < 0.01:
            target_ticker = t
            break

    if target_ticker is None or target_ticker not in returns:
        return 50.0

    sorted_rets = sorted(returns.values())
    rank = sorted_rets.index(returns[target_ticker])
    score = (rank / (len(sorted_rets) - 1)) * 100
    return float(round(score, 2))
