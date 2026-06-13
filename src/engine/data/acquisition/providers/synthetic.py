"""
Phase 5C — SyntheticProvider

First-class fallback provider. Produces deterministic, reproducible price data
for testing, rituals, offline use, and when real provider is unavailable.

This refactors the previous inline _generate_synthetic_prices logic from pull.py
into the provider abstraction.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Any
import pandas as pd
import numpy as np

from .base import BaseProvider


class SyntheticProvider(BaseProvider):
    """Always-available synthetic data provider for Phase 5C."""

    def __init__(self):
        pass

    @property
    def name(self) -> str:
        return "synthetic"

    def fetch_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d"
    ) -> Dict[str, Any]:
        """
        Generate plausible daily OHLCV data.
        Deterministic per symbol for reproducibility in rituals/tests.
        """
        if interval != "1d":
            # For v0.1, only support daily. Can extend later.
            raise ValueError("SyntheticProvider v0.1 only supports interval='1d'")

        dates = pd.date_range(start=start, end=end, freq="B")  # business days
        n = len(dates)

        if n == 0:
            n = 1
            dates = pd.date_range(start=start, periods=1)

        # Deterministic random walk based on symbol hash
        np.random.seed(hash(symbol) % (2**32))

        base_price = 150.0
        returns = np.random.normal(0.0005, 0.015, n)
        closes = base_price * (1 + returns).cumprod()
        opens = closes * (1 + np.random.normal(0, 0.003, n))
        highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.008, n)))
        lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.008, n)))
        volumes = np.random.randint(1_000_000, 15_000_000, n)

        df = pd.DataFrame({
            "date": [d.date() for d in dates],
            "open": opens.round(2),
            "high": highs.round(2),
            "low": lows.round(2),
            "close": closes.round(2),
            "volume": volumes,
        })

        return {
            "symbol": symbol.upper(),
            "data": df,
            "source": self.name,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "interval": interval,
        }
