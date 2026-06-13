"""
Phase 5A — Manifest / Log Layer (v0.1)

Creates standardized, auditable run manifests for every acquisition operation.
Manifests are the single source of truth for what data was pulled, when, why, and with what result.

All manifests are stored under data/acquisition_manifests/ in the canonical worktree.
Never stored inside the deployment repository.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import uuid

# Canonical location for manifests (governed, never in deployment tree)
MANIFEST_DIR = Path("data") / "acquisition_manifests"
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)


def _generate_run_id(run_type: str) -> str:
    """Generate a deterministic-yet-unique run identifier."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{timestamp}_{run_type}_{short_uuid}"


def create_run_manifest(
    run_type: str,                    # "ad_hoc" | "nightly"
    symbols: List[str],
    source: str,
    started_at: datetime,
    completed_at: datetime,
    status: str,                      # "success" | "partial" | "failed"
    files_written: List[str],
    errors: Optional[List[Dict[str, Any]]] = None,
    dynamic_additions: Optional[List[str]] = None,
    triggered_by: str = "manual",
    canonical_commit: Optional[str] = None,
    # Phase 5C additive fields (optional for backward compat)
    provider: Optional[str] = None,
    synthetic_fallback_used: Optional[bool] = None,
    rate_limit_events: Optional[List[Dict[str, Any]]] = None,
    retry_count: Optional[int] = None,
    api_source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a standardized acquisition run manifest.

    The returned dict is both:
    - Written to disk as JSON under data/acquisition_manifests/
    - Returned to the caller for logging / ritual validation

    This is the ONLY function allowed to create acquisition manifests.
    """
    if run_type not in {"ad_hoc", "nightly"}:
        raise ValueError(f"run_type must be 'ad_hoc' or 'nightly', got {run_type}")

    run_id = _generate_run_id(run_type)

    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "run_type": run_type,
        "started_at": started_at.isoformat() + "Z",
        "completed_at": completed_at.isoformat() + "Z",
        "source": source,
        "symbols_requested": len(symbols),
        "symbols_successful": len(files_written),
        "symbols_failed": len(symbols) - len(files_written),
        "files_written": files_written,
        "dynamic_additions": dynamic_additions or [],
        "errors": errors or [],
        "provenance": {
            "triggered_by": triggered_by,
            "canonical_commit": canonical_commit or "unknown",
        },
        "status": status,
        # Phase 5C additive fields (always present, may be None)
        "provider": provider,
        "synthetic_fallback_used": synthetic_fallback_used,
        "rate_limit_events": rate_limit_events or [],
        "retry_count": retry_count or 0,
        "api_source": api_source or source,
    }

    # Persist to canonical location
    manifest_path = MANIFEST_DIR / f"{run_id}.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    manifest["_manifest_path"] = str(manifest_path)  # convenience for callers
    return manifest


def load_manifest(run_id: str) -> Optional[Dict[str, Any]]:
    """Load a previously written manifest by run_id."""
    manifest_path = MANIFEST_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        return None
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_recent_manifests(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent manifests (newest first). Useful for ritual scripts."""
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
