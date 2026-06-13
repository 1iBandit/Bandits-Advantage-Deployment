"""
Phase 5A — Dynamic Universe Expansion & Nightly Run List (v0.1)

Responsible for identifying high-volume symbols and maintaining the persistent
list of symbols that should be included in nightly acquisition runs.

In v0.1:
- Volume discovery is simulated (returns plausible high-volume names for ritual validation).
- Real volume ranking (Polygon / other provider) will be wired in a later micro-chunk.
- The nightly run list is persisted to a simple JSON file in the canonical tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json

# Persistent storage for the symbols that participate in nightly runs
NIGHTLY_SYMBOLS_FILE = Path("data") / "acquisition_manifests" / "nightly_symbols.json"
NIGHTLY_SYMBOLS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_nightly_symbols() -> List[str]:
    if not NIGHTLY_SYMBOLS_FILE.exists():
        # Seed with a small core set that matches the existing demo universe
        seed = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "SPY", "QQQ", "DOCN"]
        _save_nightly_symbols(seed)
        return seed
    with open(NIGHTLY_SYMBOLS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("symbols", [])


def _save_nightly_symbols(symbols: List[str]) -> None:
    data = {
        "symbols": sorted(set(symbols)),
        "last_updated": "2026-06-12T00:00:00Z",  # would be real timestamp in production
    }
    with open(NIGHTLY_SYMBOLS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_dynamic_universe(
    top_equities: int = 300,
    top_etfs: int = 200,
    min_avg_volume: int = 500_000
) -> List[str]:
    """
    Returns symbols that should be considered for addition based on volume leadership.

    v0.1 implementation returns a small, deterministic set of "high volume" symbols
    for ritual validation and demo purposes. Real implementation will query a data
    provider and filter by actual average daily volume.
    """
    # Simulated high-volume names (mix of equities and ETFs that are commonly liquid)
    simulated_high_volume = [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "LLY", "JPM",
        "XOM", "UNH", "V", "MA", "HD", "COST", "PEP", "KO", "MRK", "ABBV",
        "SPY", "QQQ", "IWM", "TLT", "GLD", "SLV", "XLF", "XLE", "XLK", "XLV",
        "ARKK", "TQQQ", "SQQQ", "UVXY", "VXX",
        # A few plausible new high-volume names for expansion testing
        "PLTR", "SOFI", "RKLB", "FSLY", "DOCN", "HUMN", "BITO",
    ]

    # In a real system we would rank by actual volume here.
    # For v0.1 we just return the simulated list (the caller decides how many to take).
    return simulated_high_volume[:top_equities + top_etfs]


def update_nightly_run_list(new_symbols: List[str]) -> Dict[str, Any]:
    """
    Adds new symbols to the persistent nightly run list.

    Returns a summary useful for manifests and ritual validation.
    """
    current = set(_load_nightly_symbols())
    additions = [s.upper() for s in new_symbols if s.upper() not in current]

    if additions:
        updated = sorted(current | set(additions))
        _save_nightly_symbols(updated)
    else:
        updated = sorted(current)

    return {
        "previous_count": len(current),
        "new_count": len(updated),
        "added": additions,
        "current_symbols": updated,
    }


def get_current_nightly_symbols() -> List[str]:
    """Convenience accessor for the current persistent nightly run list."""
    return _load_nightly_symbols()
