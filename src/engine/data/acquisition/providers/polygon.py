"""
Phase 5C — PolygonProvider

Real data provider for Polygon.io.
Fetches daily (or other) aggregates using the /v2/aggs/ticker/.../range endpoint.

Requires POLYGON_API_KEY.

Handles basic errors; rate limiting is handled at a higher layer (rate_limit.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any
import os
import requests

from .base import BaseProvider


class PolygonProvider(BaseProvider):
    """Polygon.io real data provider."""

    BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("PolygonProvider requires a valid api_key")
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "polygon"

    def fetch_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d"
    ) -> Dict[str, Any]:
        """
        Fetch aggregates from Polygon.
        For v0.1, interval must be '1d'. Multiplier is 1.
        """
        if interval != "1d":
            raise ValueError("PolygonProvider v0.1 only supports daily (interval='1d')")

        # Format dates as YYYY-MM-DD
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        url = (
            f"{self.BASE_URL}/v2/aggs/ticker/{symbol.upper()}/range/1/day/"
            f"{start_str}/{end_str}"
        )
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
            "apiKey": self.api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "OK" or "results" not in data:
                raise RuntimeError(f"Polygon API error: {data.get('status')} - {data.get('error', '')}")

            results = data["results"]
            df_data = []
            for r in results:
                df_data.append({
                    "date": datetime.fromtimestamp(r["t"] / 1000).date(),
                    "open": r["o"],
                    "high": r["h"],
                    "low": r["l"],
                    "close": r["c"],
                    "volume": r["v"],
                })

            import pandas as pd
            df = pd.DataFrame(df_data)

            return {
                "symbol": symbol.upper(),
                "data": df,
                "source": self.name,
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "interval": interval,
            }

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                raise RuntimeError("Rate limit exceeded (429)") from e
            raise
        except Exception as e:
            raise RuntimeError(f"Polygon fetch failed: {e}") from e
