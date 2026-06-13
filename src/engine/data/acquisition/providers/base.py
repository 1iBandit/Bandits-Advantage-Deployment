"""
Phase 5C — BaseProvider Abstract Class

Defines the interface that all providers (real and synthetic) must implement.
This ensures interchangeability between Polygon and Synthetic paths.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any


class BaseProvider(ABC):
    """Abstract base for all data providers."""

    @abstractmethod
    def fetch_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d"
    ) -> Dict[str, Any]:
        """
        Fetch price data for the given symbol and date range.

        Returns a dict with at minimum:
        {
            "symbol": str,
            "data": list[dict] or pandas DataFrame (standardized OHLCV),
            "source": str,
            "fetched_at": str (ISO),
            "interval": str
        }
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name, e.g. 'polygon' or 'synthetic'."""
        pass
