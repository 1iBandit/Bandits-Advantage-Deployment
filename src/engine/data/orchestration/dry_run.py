"""
Phase 5B — Dry-Run Simulation (v0.1)

Provides preview/simulation of orchestration runs without side effects.
Used for validation, planning, and the ritual script.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.engine.data.acquisition import get_dynamic_universe, get_current_nightly_symbols


def simulate_nightly_run() -> Dict[str, Any]:
    """
    Returns a preview of what the next nightly run would do
    (symbols to be pulled, estimated new dynamic additions, etc.)
    without actually writing data or manifests.
    """
    current_symbols = get_current_nightly_symbols()
    dynamic = get_dynamic_universe()

    # Estimate additions: symbols in dynamic but not in current
    potential_additions = [s for s in dynamic if s not in current_symbols]

    return {
        "run_type": "nightly",
        "estimated_symbols_to_process": len(current_symbols) + len(potential_additions),
        "current_nightly_symbols": len(current_symbols),
        "estimated_dynamic_additions": len(potential_additions),
        "potential_new_symbols": potential_additions[:10],  # sample
        "note": "This is a dry-run preview. No data or manifests were written.",
    }
