"""
Phase 5A — Nightly Acquisition Orchestration (v0.1)

Coordinates the full nightly run:
- Loads the current persistent nightly symbols (core + previously added dynamic)
- Optionally merges fresh dynamic universe symbols
- Pulls each symbol (delegates to pull.py)
- Produces a single top-level run manifest

This module is intentionally thin on business logic — it orchestrates the other
modules in the acquisition package.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .pull import pull_symbol
from .universe import get_dynamic_universe, update_nightly_run_list, get_current_nightly_symbols
from .manifest import create_run_manifest


def run_nightly_acquisition(
    universe: Optional[List[str]] = None,
    include_dynamic: bool = True,
    source: str = "synthetic",
    dry_run: bool = False,
    triggered_by: str = "nightly_scheduler",
    canonical_commit: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a full nightly acquisition run.

    Returns a summary that includes the top-level manifest.
    When dry_run=True, no files are written and no network calls are made
    (useful for ritual validation and smoke testing).
    """
    started_at = datetime.utcnow()

    # 1. Determine the effective universe for this run
    core_symbols = universe or get_current_nightly_symbols()

    dynamic_additions: List[str] = []
    if include_dynamic:
        dynamic = get_dynamic_universe()
        # Only add symbols that are not already in the core list
        dynamic_additions = [s for s in dynamic if s not in core_symbols]
        if dynamic_additions and not dry_run:
            update_nightly_run_list(dynamic_additions)

    effective_universe = sorted(set(core_symbols) | set(dynamic_additions))

    if not effective_universe:
        completed_at = datetime.utcnow()
        manifest = create_run_manifest(
            run_type="nightly",
            symbols=[],
            source=source,
            started_at=started_at,
            completed_at=completed_at,
            status="success",
            files_written=[],
            errors=None,
            dynamic_additions=dynamic_additions,
            triggered_by=triggered_by,
            canonical_commit=canonical_commit,
        )
        return {"status": "success", "symbols_processed": 0, "manifest": manifest}

    # 2. Pull each symbol
    files_written: List[str] = []
    errors: List[Dict[str, Any]] = []

    for symbol in effective_universe:
        if dry_run:
            # Simulate success without touching disk
            files_written.append(f"data/raw/prices/{symbol}.csv (dry_run)")
            continue

        try:
            result = pull_symbol(
                symbol=symbol,
                source=source,
                interval="1d",
                lookback_days=730,
                force_refresh=False,
                triggered_by=triggered_by,
                canonical_commit=canonical_commit,
            )
            if result.get("status") == "success":
                files_written.append(result["file_path"])
            else:
                errors.append({"symbol": symbol, "error": result})
        except Exception as exc:  # broad for v0.1; will be tightened with real providers
            errors.append({"symbol": symbol, "error": str(exc)})

    completed_at = datetime.utcnow()
    status = "success" if not errors else ("partial" if files_written else "failed")

    manifest = create_run_manifest(
        run_type="nightly",
        symbols=effective_universe,
        source=source,
        started_at=started_at,
        completed_at=completed_at,
        status=status,
        files_written=files_written,
        errors=errors or None,
        dynamic_additions=dynamic_additions,
        triggered_by=triggered_by,
        canonical_commit=canonical_commit,
    )

    return {
        "status": status,
        "symbols_requested": len(effective_universe),
        "symbols_successful": len(files_written),
        "symbols_failed": len(errors),
        "dynamic_additions": dynamic_additions,
        "manifest": manifest,
    }
