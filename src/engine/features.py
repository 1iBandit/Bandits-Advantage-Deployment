"""
Technical feature computation for Bandit's Advantage v3 (Phase 2).

This module implements the core indicators required to populate TickerScore
objects (except Bandit's Rocket and final_rank, which are Phase 3+).

All functions are pure where possible and accept/return pandas objects for
easy integration with the data readers and pipeline.

Formulas are standard TA unless explicitly noted as "Bandit custom approximation".
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from .models.core import TickerScore, EngineConfig, FeatureDict


# =============================================================================
# Core Technical Indicators (standard, well-tested implementations)
# =============================================================================

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI (0-100)."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val.fillna(50.0)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range (Wilder)."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def atr_pct(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ATR expressed as percentage of close (most useful for ranking)."""
    atr_val = atr(high, low, close, period)
    return (atr_val / close) * 100


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average Directional Index (ADX).
    Returns the ADX line only (0-100). +DI/-DI available if needed later.
    """
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = atr(high, low, close, period)  # reuse smoothed TR

    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / tr
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / tr

    dx = (np.abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx_val = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_val.fillna(20.0)


# =============================================================================
# Phase 2 Feature Set (the 8 requested + a few v2-visible helpers)
# =============================================================================

def relative_strength_vs_spy(
    ticker_df: pd.DataFrame, spy_df: pd.DataFrame, window: int = 63
) -> float:
    """
    Simple relative strength vs benchmark (SPY by default).
    Ratio of cumulative returns over the window.
    """
    if spy_df is None or len(spy_df) < window + 5:
        return 1.0

    t_ret = ticker_df["Close"].pct_change(window).iloc[-1]
    s_ret = spy_df["Close"].pct_change(window).iloc[-1]

    if pd.isna(s_ret) or s_ret == 0:
        return 1.0
    return (1 + t_ret) / (1 + s_ret) - 1   # excess return style number


def relative_breadth_score(
    ticker: str, prices: Dict[str, pd.DataFrame], window: int = 63
) -> float:
    """
    Cross-sectional breadth participation (Bandit custom approximation for Phase 2).

    Returns a 0-100 score representing how the ticker's recent momentum ranks
    within the full universe. Higher = stronger relative momentum vs peers.
    """
    if ticker not in prices or len(prices) < 5:
        return 50.0

    returns = {}
    for t, df in prices.items():
        if len(df) > window + 5:
            r = df["Close"].pct_change(window).iloc[-1]
            if not pd.isna(r):
                returns[t] = r

    if ticker not in returns or len(returns) < 3:
        return 50.0

    sorted_rets = sorted(returns.values())
    rank = sorted_rets.index(returns[ticker])
    score = (rank / (len(sorted_rets) - 1)) * 100
    return round(score, 2)


def raw_expected_ranges(
    close: pd.Series, atr_pct_series: pd.Series, factor: float = 1.5
) -> tuple[float, float]:
    """
    Raw expected move ranges for 12 weeks and 12 months (Bandit approximation).

    Uses recent ATR% scaled by sqrt(time) and a factor.
    In v2 this was more sophisticated (vol surface + historical quantiles).
    """
    if len(atr_pct_series) < 20:
        return (8.0, 22.0)  # sensible defaults

    recent_atr_pct = atr_pct_series.tail(20).mean()

    # Rough trading day counts
    days_12w = 63
    days_12m = 252

    exp_12w = recent_atr_pct * factor * np.sqrt(days_12w / 20)
    exp_12m = recent_atr_pct * factor * np.sqrt(days_12m / 20)

    return round(exp_12w, 1), round(exp_12m, 1)


def short_term_movement_intensity(close: pd.Series, window: int = 20) -> float:
    """
    Short-term realized movement intensity (Bandit custom).

    Normalized standard deviation of daily returns over a short window.
    Higher values = more violent short-term action.
    """
    rets = close.pct_change().dropna().tail(window)
    if len(rets) < 5:
        return 1.8
    intensity = rets.std() * 100 * np.sqrt(252)  # annualized-ish
    return round(float(intensity), 2)


def momentum_pulse(
    close: pd.Series, rsi_series: pd.Series, vol_momentum: Optional[float] = None, window: int = 10
) -> float:
    """
    Momentum Pulse (Bandit custom composite for Phase 2).

    Combines:
    - Slope of RSI over short window (normalized)
    - Recent price momentum
    - Optional 12w vol momentum

    Output is a z-like score centered around 0 (positive = accelerating momentum).
    """
    rsi_slope = rsi_series.diff(window).tail(5).mean()
    price_mom = close.pct_change(10).iloc[-1] * 100 if len(close) > 10 else 0.0

    pulse = (rsi_slope * 0.6) + (price_mom * 0.4)
    if vol_momentum is not None:
        pulse += vol_momentum * 0.25

    return round(float(pulse), 3)


# =============================================================================
# High-level orchestrator used by the pipeline
# =============================================================================

def compute_features_for_universe(
    prices: Dict[str, pd.DataFrame],
    spy_df: Optional[pd.DataFrame] = None,
    config: Optional[EngineConfig] = None,
) -> Dict[str, FeatureDict]:
    """
    Compute all Phase 2 features for every ticker in the universe.

    Returns a dict {ticker: {feature_name: value, ...}} ready to be turned
    into TickerScore objects.
    """
    cfg = config or EngineConfig()
    results: Dict[str, FeatureDict] = {}

    for ticker, df in prices.items():
        if len(df) < 60:
            continue

        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        rsi_val = rsi(close, cfg.rsi_period).iloc[-1]
        atrp = atr_pct(high, low, close, cfg.atr_period).iloc[-1]
        adx_val = adx(high, low, close, cfg.adx_period).iloc[-1]

        rs = relative_strength_vs_spy(df, spy_df, cfg.rs_window) if spy_df is not None else 0.0

        breadth = relative_breadth_score(ticker, prices, cfg.rs_window)

        exp_12w, exp_12m = raw_expected_ranges(close, atr_pct(high, low, close, cfg.atr_period), cfg.expected_range_factor)

        # 12w vol momentum (simple proxy used by several v2 columns)
        vol_mom = close.pct_change(63).iloc[-1] * 100 if len(close) > 70 else 0.0

        sti = short_term_movement_intensity(close)
        pulse = momentum_pulse(close, rsi(close, cfg.rsi_period), vol_mom)

        # === Acceleration / Transition Features v1 (legacy path) ===
        # Duplicated simple logic here because legacy compute_features_for_universe
        # has its own non-modular implementations. Kept tiny + defensive.
        rsi_s = rsi(close, cfg.rsi_period)
        rsi_accel = 0.0
        if len(rsi_s) > 3:
            rsi_accel = float(rsi_s.iloc[-1] - rsi_s.iloc[-4])

        atr_s = atr_pct(high, low, close, cfg.atr_period)
        vol_flag = 0.0
        if len(atr_s) >= 20:
            med = float(atr_s.tail(20).median())
            curr = float(atr_s.iloc[-1])
            vol_flag = 1.0 if curr > med else 0.0

        # v5: RS Acceleration (simple slope using recent vs prior excess)
        rs_accel = 0.0
        if spy_df is not None and len(df) > 10:
            try:
                t_ret = close.iloc[-1] / close.iloc[-6] - 1 if len(close) > 5 else 0.0
                s_ret = spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[-6] - 1 if len(spy_df) > 5 else 0.0
                recent_rs = t_ret - s_ret
                t_ret_past = close.iloc[-6] / close.iloc[-11] - 1 if len(close) > 10 else recent_rs
                s_ret_past = spy_df["Close"].iloc[-6] / spy_df["Close"].iloc[-11] - 1 if len(spy_df) > 10 else s_ret
                past_rs = t_ret_past - s_ret_past
                if abs(past_rs) > 0.0001:
                    rs_accel = round( (recent_rs - past_rs) / abs(past_rs) , 4)
            except Exception:
                rs_accel = 0.0

        results[ticker] = {
            "rsi": round(float(rsi_val), 2),
            "atr_pct": round(float(atrp), 3),
            "adx": round(float(adx_val), 2),
            "rs_vs_spy": round(float(rs), 4),
            "relative_breadth_score": breadth,
            "raw_expected_range_12w": exp_12w,
            "raw_expected_range_12m": exp_12m,
            "short_term_movement_intensity": sti,
            "momentum_pulse": pulse,
            "vol_momentum_12w": round(float(vol_mom), 2),
            # New acceleration features (v1)
            "rsi_acceleration": round(float(rsi_accel), 4),
            "volatility_expansion_flag": vol_flag,
            "rs_acceleration": round(float(rs_accel), 4),  # v5 feat_rs_acceleration
        }

    return results


def build_ticker_scores(
    feature_dict: Dict[str, FeatureDict],
    prices: Dict[str, pd.DataFrame],
    as_of: date,
    config: Optional[EngineConfig] = None,
) -> list[TickerScore]:
    """
    Convert raw feature dicts into fully populated TickerScore objects (Phase 2).
    """
    scores: list[TickerScore] = []

    for ticker, feats in feature_dict.items():
        if ticker not in prices:
            continue
        close = float(prices[ticker]["Close"].iloc[-1])

        score = TickerScore(
            ticker=ticker,
            as_of=as_of,
            close=close,
            rsi=feats["rsi"],
            atr_pct=feats["atr_pct"],
            adx=feats["adx"],
            rs_vs_spy=feats["rs_vs_spy"],
            relative_breadth_score=feats["relative_breadth_score"],
            raw_expected_range_12w=feats["raw_expected_range_12w"],
            raw_expected_range_12m=feats["raw_expected_range_12m"],
            short_term_movement_intensity=feats["short_term_movement_intensity"],
            momentum_pulse=feats["momentum_pulse"],
            vol_momentum_12w=feats.get("vol_momentum_12w"),
            # Acceleration v1
            rsi_acceleration=feats.get("rsi_acceleration", 0.0),
            volatility_expansion_flag=feats.get("volatility_expansion_flag", 0.0),
            rs_acceleration=feats.get("rs_acceleration", 0.0),  # v5
        )
        scores.append(score)

    return scores
