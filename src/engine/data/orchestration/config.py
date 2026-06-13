"""
Phase 5B — Orchestration Configuration (v0.1)

Central place for orchestration thresholds, retry policies, and manifest paths.
Kept minimal for v0.1; will expand with real scheduling integration.
"""

from __future__ import annotations

from typing import Dict, Any

# Default paths (aligned with 5A)
ORCHESTRATION_MANIFEST_DIR = "data/orchestration_manifests"

# Basic retry policy defaults (used by failure.py and future scheduler)
DEFAULT_RETRY_POLICY: Dict[str, Any] = {
    "max_retries": 3,
    "backoff_seconds": 60,
    "rate_limit_backoff": 300,
}

# Manifest retention (future use)
MANIFEST_RETENTION_DAYS = 90


def get_orchestration_config() -> Dict[str, Any]:
    """Return the current orchestration configuration."""
    return {
        "manifest_dir": ORCHESTRATION_MANIFEST_DIR,
        "retry_policy": DEFAULT_RETRY_POLICY.copy(),
        "manifest_retention_days": MANIFEST_RETENTION_DAYS,
    }
