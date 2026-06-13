"""
Phase 5A — Thin Adapters (v0.1)

These functions provide a clean, narrow interface between the acquisition layer
and the rest of the system (Phase 3 readers and Phase 4 snapshot / lifecycle mechanisms).

CRITICAL: These adapters must contain ZERO business logic, scoring, or decision making.
They are purely translation / discovery helpers.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# In a real system these would be proper imports from the Phase 3 layer.
# For v0.1 we keep them as lightweight callables so the contract can be validated
# without creating circular dependencies during early implementation.


def get_price_reader_for_symbol(symbol: str) -> Callable[[str], Any]:
    """
    Returns a callable that can read the most recent price data for the symbol
    from the canonical storage.

    The returned callable should be compatible with existing Phase 3 data readers.
    """
    # Placeholder — in a later micro-chunk this will return the actual reader
    # from src/engine/data/readers or the pipeline ingest layer.
    def _reader(symbol: str) -> Dict[str, Any]:
        return {"symbol": symbol.upper(), "note": "thin adapter placeholder - real reader wired later"}

    return _reader


def build_snapshot_from_acquisition(
    symbols: List[str],
    as_of: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Thin wrapper intended to eventually call into the Phase 4 snapshot builders
    (build_portfolio_snapshot, etc.) using data that was just acquired.

    In v0.1 this is a no-op placeholder that documents the intended handoff point.
    Real implementation will live in a future micro-chunk after the acquisition
    layer is proven stable.
    """
    return {
        "symbols": [s.upper() for s in symbols],
        "as_of": as_of or "latest",
        "note": "thin adapter placeholder — will delegate to Phase 4 snapshot builders",
    }
