"""
Phase 5B — Core Orchestration Logic (v0.1)

Implements run_nightly_orchestration and run_ad_hoc_orchestration.
These delegate to Phase 5A for actual acquisition, then create linked 5B manifests.
Supports dry-run and basic failure handling via the failure module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.engine.data.acquisition import (
    run_nightly_acquisition,
    pull_symbol,
    get_current_nightly_symbols,
)
from .manifest import create_orchestration_manifest
from .failure import classify_failure
from .dry_run import simulate_nightly_run


def run_nightly_orchestration(
    dry_run: bool = False,
    force: bool = False
) -> Dict[str, Any]:
    """
    Executes the full nightly flow:
    1. (Optional) simulate if dry_run
    2. Calls Phase 5A acquisition
    3. Creates 5B orchestration manifest linked to 5A manifests
    4. Returns summary + status
    """
    started_at = datetime.utcnow()

    if dry_run:
        preview = simulate_nightly_run()
        completed_at = datetime.utcnow()
        # Still create a manifest for audit, but mark as dry
        manifest = create_orchestration_manifest(
            run_type="nightly",
            triggered_by="dry_run_simulation",
            phase5a_manifest_ids=[],
            symbols_processed=[],
            status="dry_run",
            started_at=started_at,
            completed_at=completed_at,
            errors=None,
        )
        return {
            "status": "dry_run",
            "preview": preview,
            "manifest": manifest,
            "note": "No actual acquisition performed.",
        }

    # Delegate to Phase 5A
    phase5a_result = run_nightly_acquisition(
        include_dynamic=True,
        dry_run=False,
        triggered_by="orchestration_nightly",
    )

    phase5a_manifest_id = phase5a_result.get("manifest", {}).get("run_id", "unknown_5a")
    phase5a_manifest_ids = [phase5a_manifest_id] if phase5a_manifest_id != "unknown_5a" else []

    symbols_processed = phase5a_result.get("symbols_processed", [])  # if 5A returns list, else count
    # For v0.1, use count if list not available
    if isinstance(symbols_processed, int):
        symbols_processed = []  # placeholder

    status = phase5a_result.get("status", "success")
    errors = phase5a_result.get("errors", [])

    completed_at = datetime.utcnow()

    orchestration_manifest = create_orchestration_manifest(
        run_type="nightly",
        triggered_by="nightly_orchestrator",
        phase5a_manifest_ids=phase5a_manifest_ids,
        symbols_processed=symbols_processed,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        errors=errors,
    )

    return {
        "status": status,
        "phase5a_result": phase5a_result,
        "orchestration_manifest": orchestration_manifest,
    }


def run_ad_hoc_orchestration(
    symbols: List[str],
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Triggers acquisition + orchestration for a specific set of symbols on demand.
    Returns linked 5A + 5B manifests.
    """
    started_at = datetime.utcnow()

    if dry_run:
        completed_at = datetime.utcnow()
        manifest = create_orchestration_manifest(
            run_type="ad_hoc",
            triggered_by="dry_run_adhoc",
            phase5a_manifest_ids=[],
            symbols_processed=symbols,
            status="dry_run",
            started_at=started_at,
            completed_at=completed_at,
        )
        return {
            "status": "dry_run",
            "symbols": symbols,
            "manifest": manifest,
        }

    phase5a_manifest_ids = []
    errors = []

    for symbol in symbols:
        try:
            res = pull_symbol(symbol, triggered_by="ad_hoc_orchestration")
            if res.get("status") == "success":
                m_id = res.get("manifest", {}).get("run_id")
                if m_id:
                    phase5a_manifest_ids.append(m_id)
            else:
                errors.append({"symbol": symbol, "error": res})
        except Exception as e:
            classified = classify_failure(e)
            errors.append({"symbol": symbol, "error": str(e), "classification": classified})

    completed_at = datetime.utcnow()
    status = "success" if not errors else ("partial" if phase5a_manifest_ids else "failed")

    orchestration_manifest = create_orchestration_manifest(
        run_type="ad_hoc",
        triggered_by="ad_hoc_orchestrator",
        phase5a_manifest_ids=phase5a_manifest_ids,
        symbols_processed=symbols,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        errors=errors or None,
    )

    return {
        "status": status,
        "phase5a_manifest_ids": phase5a_manifest_ids,
        "orchestration_manifest": orchestration_manifest,
        "errors": errors,
    }
