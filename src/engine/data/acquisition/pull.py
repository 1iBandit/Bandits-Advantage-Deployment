"""
Phase 5C — Ad-hoc & Single-Symbol Pull Logic (v0.1)

Responsible for on-demand data acquisition for any symbol.
All data is written to the canonical location:
    data/raw/prices/<SYMBOL>.csv

This module MUST remain a pure service layer. No scoring, no features, no decisions.

Phase 5C integration: uses the provider abstraction for real (Polygon) or synthetic data.
Public API of pull_symbol remains unchanged for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .manifest import create_run_manifest
from .providers.factory import get_provider
from .providers.base import BaseProvider

# Canonical storage root (never inside deployment tree)
PRICE_DATA_DIR = Path("data") / "raw" / "prices"
PRICE_DATA_DIR.mkdir(parents=True, exist_ok=True)


def pull_symbol(
    symbol: str,
    source: str = "synthetic",   # kept for backward compat; now resolved via provider
    interval: str = "1d",
    lookback_days: int = 730,
    force_refresh: bool = False,
    triggered_by: str = "manual",
    canonical_commit: Optional[str] = None,
    provider: Optional[BaseProvider] = None,
) -> Dict[str, Any]:
    """
    Pull price data for a single symbol and persist it to the canonical location.

    If provider is None, resolves via get_provider() (real if key available, else synthetic).
    Public signature unchanged for 5A/5B ritual compatibility.

    Returns a result dict suitable for manifest creation and ritual validation.
    """
    started_at = datetime.utcnow()
    symbol = symbol.upper().strip()

    if not symbol:
        raise ValueError("symbol must be provided")

    file_path = PRICE_DATA_DIR / f"{symbol}.csv"

    end = datetime.utcnow()
    start = end - timedelta(days=lookback_days)

    # Resolve provider (Phase 5C)
    if provider is None:
        # Map legacy 'source' param for backward compat; prefer real if available
        prefer_real = source.lower() != "synthetic"
        provider = get_provider(prefer_real=prefer_real)

    # Fetch via provider
    fetched = provider.fetch_prices(symbol, start, end, interval)

    df: pd.DataFrame = fetched["data"]
    provider_name = fetched.get("source", provider.name)

    # Write / overwrite (legacy)
    df.to_csv(file_path, index=False)

    # Dual-write to SOT raw (prices_raw) — part of migration F + production backbone
    try:
        from src.sot.migrate import dual_write_price
        # Normalize df rows for SOT
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "date": str(r.get("date") or r.get("Date", "")),
                "open": r.get("open") or r.get("Open"),
                "high": r.get("high") or r.get("High"),
                "low": r.get("low") or r.get("Low"),
                "close": r.get("close") or r.get("Close"),
                "volume": r.get("volume") or r.get("Volume"),
                "adj_close": r.get("adj_close") or r.get("Adj Close"),
                "source": provider_name,
            })
        dual_write_price(symbol, rows)
    except Exception:
        # Non-fatal — legacy path continues
        pass

    completed_at = datetime.utcnow()
    files_written = [str(file_path)]

    # Determine if fallback was used (for manifest)
    synthetic_fallback_used = provider_name == "synthetic" and source.lower() != "synthetic"

    # Create auditable manifest (extended for 5C)
    manifest = create_run_manifest(
        run_type="ad_hoc",
        symbols=[symbol],
        source=provider_name,
        started_at=started_at,
        completed_at=completed_at,
        status="success",
        files_written=files_written,
        errors=None,
        dynamic_additions=[],
        triggered_by=triggered_by,
        canonical_commit=canonical_commit,
        # 5C additive fields
        provider=provider_name,
        synthetic_fallback_used=synthetic_fallback_used,
        rate_limit_events=[],  # populated by caller/orchestration if needed
        retry_count=0,
        api_source=provider_name,
    )

    return {
        "status": "success",
        "symbol": symbol,
        "file_path": str(file_path),
        "rows_written": len(df),
        "manifest": manifest,
        "provenance": manifest["provenance"],
        "provider": provider_name,
        "synthetic_fallback_used": synthetic_fallback_used,
    }
