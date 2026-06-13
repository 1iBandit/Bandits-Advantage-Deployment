"""
Phase 5B — Thin Public Entry Points (v0.1)

These are the clean, importable functions for triggering orchestration.
They delegate to the runner and remain extremely thin.
Future CLI, scheduler, or UI can call these without knowing internal details.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .runner import run_nightly_orchestration, run_ad_hoc_orchestration
from .manifest import load_orchestration_manifest, list_recent_orchestration_manifests


def trigger_nightly(dry_run: bool = False) -> Dict[str, Any]:
    """Thin entry point for nightly orchestration."""
    return run_nightly_orchestration(dry_run=dry_run)


def trigger_ad_hoc(symbols: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Thin entry point for ad-hoc orchestration on specific symbols."""
    return run_ad_hoc_orchestration(symbols=symbols, dry_run=dry_run)


def get_last_orchestration_status() -> Dict[str, Any]:
    """Returns status of the most recent orchestration run."""
    recent = list_recent_orchestration_manifests(limit=1)
    if not recent:
        return {"status": "none", "message": "No orchestration runs found yet."}
    last = recent[0]
    return {
        "orchestration_run_id": last.get("orchestration_run_id"),
        "run_type": last.get("run_type"),
        "status": last.get("status"),
        "started_at": last.get("started_at"),
        "completed_at": last.get("completed_at"),
        "phase5a_manifests": last.get("phase5a_manifests", []),
        "symbols_processed": last.get("symbols_processed"),
        "_manifest_path": last.get("_manifest_path"),
    }
