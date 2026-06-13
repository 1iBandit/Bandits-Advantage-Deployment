"""
Data readers for Bandit's Advantage v3 (Phase 2).

Responsibilities:
- Load ticker universe (hardcoded list or file)
- Load reference / metadata
- Ingest OHLCV price history (CSV dir, single file, or in-memory)
- Provide high-quality synthetic data generator for development & tests

All readers are side-effect free except for filesystem access when a real path is supplied.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

from ..models.core import EngineConfig, PriceDict


# ---------------------------------------------------------------------------
# Ticker universe & reference data (Phase 2 minimal viable)
# ---------------------------------------------------------------------------

DEFAULT_TICKERS: List[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "AMD", "SMCI",
    "SPY", "QQQ", "IWM", "TLT", "GLD",
    "JPM", "XOM", "UNH", "V", "MA",
]


def load_ticker_universe(config: Optional[EngineConfig] = None) -> List[str]:
    """Return the list of tickers to process for this run.

    Note: This is legacy support. New code should prefer engine.pipeline.universe.build_universe()
    which properly handles the `tickers` (ad-hoc) vs `ticker_universe` + dynamic expansion modes.
    """
    if config:
        # Prefer the newer ad-hoc `tickers` field for consistency with build_universe design
        if getattr(config, "tickers", None):
            return [t.upper() for t in config.tickers]
        if config.ticker_universe:
            return [t.upper() for t in config.ticker_universe]
    # Future: support config.data_path / tickers.csv
    return DEFAULT_TICKERS.copy()


def load_reference_data(tickers: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Phase 2 stub. Returns minimal reference metadata.
    In a real implementation this would load sector, industry, market-cap bucket, etc.
    """
    ref: Dict[str, Dict[str, str]] = {}
    for t in tickers:
        ref[t] = {
            "sector": "Technology" if t in {"AAPL", "MSFT", "NVDA", "AMD"} else "Other",
            "industry": "Semiconductors" if t in {"NVDA", "AMD", "AVGO"} else "Broad",
        }
    return ref


# ---------------------------------------------------------------------------
# Synthetic price generator (deterministic, realistic enough for feature dev)
# ---------------------------------------------------------------------------

def generate_synthetic_ohlcv(
    tickers: List[str],
    n_days: int = 400,
    seed: int = 42,
    start_date: Optional[date] = None,
) -> PriceDict:
    """
    Generate deterministic synthetic daily OHLCV for the given tickers.

    Uses a simple geometric Brownian motion + occasional volatility spikes.
    All tickers share a common market factor so cross-sectional features
    (RS vs SPY, Relative Breadth) are meaningful.
    """
    rng = np.random.default_rng(seed)
    if start_date is None:
        start_date = date.today() - timedelta(days=n_days + 10)

    dates = pd.bdate_range(start=start_date, periods=n_days)

    prices: PriceDict = {}
    market_factor = rng.normal(0.0004, 0.012, size=n_days)  # common market drift/vol

    for i, ticker in enumerate(tickers):
        # Per-ticker idiosyncratic vol and drift
        idio_vol = 0.018 + rng.uniform(-0.004, 0.012)
        idio_drift = 0.0003 + rng.uniform(-0.0004, 0.0008)

        rets = idio_drift + 0.65 * market_factor + rng.normal(0, idio_vol, size=n_days)
        # Occasional gap / event
        event_mask = rng.random(n_days) < 0.008
        rets[event_mask] += rng.normal(0, 0.045, size=event_mask.sum())

        close = 50 + np.cumsum(rets) * 80  # start around $50-150 range
        close = np.clip(close, 3.0, 800.0)

        high = close * (1 + np.abs(rng.normal(0, 0.008, size=n_days)))
        low = close * (1 - np.abs(rng.normal(0, 0.008, size=n_days)))
        open_ = close + rng.normal(0, close * 0.004, size=n_days)
        volume = rng.integers(800_000, 45_000_000, size=n_days).astype(float)

        df = pd.DataFrame(
            {
                "Open": np.round(open_, 2),
                "High": np.round(high, 2),
                "Low": np.round(low, 2),
                "Close": np.round(close, 2),
                "Volume": volume,
            },
            index=dates,
        )
        df.index.name = "Date"
        prices[ticker] = df

    return prices


# ---------------------------------------------------------------------------
# Real data loaders (stubs ready for extension)
# ---------------------------------------------------------------------------

def load_ohlcv_from_csv_dir(directory: Union[str, Path], tickers: List[str]) -> PriceDict:
    """Load one CSV per ticker from a directory. Expected columns: Date,Open,High,Low,Close,Volume."""
    directory = Path(directory)
    prices: PriceDict = {}
    for t in tickers:
        path = directory / f"{t}.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
            prices[t] = df.sort_index()
    return prices


def load_price_history(config: EngineConfig, tickers: List[str]) -> PriceDict:
    """
    Main entry point for Phase 2 price loading.
    Dispatches based on config.data_source (now includes "polygon" / "polygon_cache").
    """
    source = (config.data_source or "synthetic").lower()

    if source == "synthetic":
        return generate_synthetic_ohlcv(
            tickers,
            n_days=config.synthetic_days,
            seed=config.synthetic_seed,
        )

    if source in {"csv_dir", "csv"} and config.data_path:
        return load_ohlcv_from_csv_dir(config.data_path, tickers)

    if source in {"polygon", "polygon_cache"}:
        # Delegate to the primary io implementation (handles cache + fetch logic + new batch/resilience)
        from engine.io import readers as io_readers
        cache_only = source == "polygon_cache"
        return io_readers.fetch_polygon_ohlcv(
            tickers,
            prices_dir=config.data_path,
            benchmark="SPY",
            lookback_days=config.synthetic_days or 400,
            batch_size=getattr(config, "polygon_batch_size", 15),
            batch_pause_seconds=getattr(config, "polygon_batch_pause_seconds", 2.0),
            max_retries=getattr(config, "polygon_max_retries", 4),
            cache_only=cache_only,
        )

    # Future: parquet, single wide csv, database, yfinance cache, etc.
    # For now fall back to synthetic with a warning in real usage.
    return generate_synthetic_ohlcv(tickers, n_days=config.synthetic_days, seed=config.synthetic_seed)


def load_spy_benchmark(prices: PriceDict) -> Optional[pd.DataFrame]:
    """Return the SPY (or configured benchmark) dataframe if present in the price dict."""
    for candidate in ("SPY", "SPX", "IWM", "QQQ"):
        if candidate in prices:
            return prices[candidate].copy()
    # If no explicit benchmark, caller can synthesize or skip RS features
    return None
