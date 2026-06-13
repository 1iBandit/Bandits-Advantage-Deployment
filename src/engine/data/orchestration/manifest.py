"""
Phase 5B — Orchestration Manifest Layer (v0.1)

Creates standardized 5B orchestration manifests that link to underlying 5A acquisition manifests.
This provides the auditable chain: 5B orchestration run → one or more 5A acquisition manifests.

All manifests are stored under data/orchestration_manifests/ in the canonical worktree.
Never stored inside the deployment repository.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import uuid

# Canonical location for 5B orchestration manifests (governed, never in deployment tree)
MANIFEST_DIR = Path("data") / "orchestration_manifests"
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)


def _generate_run_id(run_type: str) -> str:
    """Generate a deterministic-yet-unique run identifier."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{timestamp}_{run_type}_{short_uuid}"


def create_orchestration_manifest(
    run_type: str,                    # "nightly" | "ad_hoc"
    triggered_by: str,
    phase5a_manifest_ids: List[str],  # Links to Phase 5A run_ids
    symbols_processed: List[str],
    status: str,                      # "success" | "partial" | "failed"
    started_at: datetime,
    completed_at: datetime,
    errors: Optional[List[Dict[str, Any]]] = None,
    canonical_commit: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a 5B orchestration manifest that references the underlying 5A acquisition manifests.
    This is the ONLY function allowed to create orchestration manifests.
    """
    if run_type not in {"nightly", "ad_hoc"}:
        raise ValueError(f"run_type must be 'nightly' or 'ad_hoc', got {run_type}")

    run_id = _generate_run_id(run_type)

    manifest: Dict[str, Any] = {
        "orchestration_run_id": run_id,
        "run_type": run_type,
        "started_at": started_at.isoformat() + "Z",
        "completed_at": completed_at.isoformat() + "Z",
        "status": status,
        "phase5a_manifests": phase5a_manifest_ids or [],
        "symbols_processed": len(symbols_processed),
        "errors": errors or [],
        "triggered_by": triggered_by,
        "canonical_commit": canonical_commit or "unknown",
        # Phase 5C additive fields (propagated from 5A if present)
        "provider": None,  # will be enriched from linked 5A manifests at higher level if needed
        "synthetic_fallback_used": None,
        "rate_limit_events": [],
        "retry_count": 0,
        "api_source": None,
    }

    # Persist to canonical location
    manifest_path = MANIFEST_DIR / f"{run_id}.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    manifest["_manifest_path"] = str(manifest_path)  # convenience for callers
    return manifest


def load_orchestration_manifest(run_id: str) -> Optional[Dict[str, Any]]:
    """Load a previously written 5B orchestration manifest by run_id."""
    manifest_path = MANIFEST_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        return None
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_recent_orchestration_manifests(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent 5B orchestration manifests (newest first)."""
    files = sorted(MANIFEST_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    manifests = []
    for f in files[:limit]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                m = json.load(fh)
                m["_manifest_path"] = str(f)
                manifests.append(m)
        except Exception:
            continue
    return manifests
