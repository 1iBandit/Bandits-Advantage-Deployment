"""
Phase 5B — Scheduling & Orchestration Layer (v0.1)

Isolated module for manifest-driven orchestration of Phase 5A acquisition runs.
Provides governed entry points for nightly and ad-hoc runs, dry-run support,
failure handling, and linkage between 5B orchestration manifests and 5A acquisition manifests.

All logic is strictly an orchestration/service layer:
- No acquisition logic (delegates to Phase 5A)
- No scoring, features, or decisions
- No leakage into narrative.py, analyst_workbench.py, or Phase 4L presenters

See Phase5B_Scheduling_Orchestration_Contract_v0.1.md for full contract.
"""

from .manifest import create_orchestration_manifest
from .runner import run_nightly_orchestration, run_ad_hoc_orchestration
from .dry_run import simulate_nightly_run
from .failure import classify_failure
from .entry import trigger_nightly, trigger_ad_hoc, get_last_orchestration_status

__all__ = [
    "create_orchestration_manifest",
    "run_nightly_orchestration",
    "run_ad_hoc_orchestration",
    "simulate_nightly_run",
    "classify_failure",
    "trigger_nightly",
    "trigger_ad_hoc",
    "get_last_orchestration_status",
]
