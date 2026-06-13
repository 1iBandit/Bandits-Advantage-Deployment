"""
Portfolio Layer Persistence (Phase 1 – Chunk B + Phase 2 Chunk F enhancements)

Minimal append-only JSONL persistence for PortfolioStateSnapshot.

- Uses JSONL (one JSON object per line)
- Human-inspectable and debuggable
- Respects Phase 1 guardrails + Phase 2 version hygiene
- Graceful loading of v1.0 (pre-intelligence) and v1.1+ (enriched) snapshots
- No mutations; append-only
"""

import json
from pathlib import Path
from datetime import date, datetime
from dataclasses import asdict, fields as dc_fields
from typing import List, Optional

from ..models.portfolio import PortfolioStateSnapshot, HoldingSnapshot


def _json_default(obj):
    """JSON serializer for date/datetime objects."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _serialize_snapshot(snapshot: PortfolioStateSnapshot) -> str:
    """Convert snapshot to a single JSONL line."""
    data = asdict(snapshot)
    return json.dumps(data, default=_json_default) + "\n"


def _deserialize_snapshot(data: dict) -> PortfolioStateSnapshot:
    """
    Reconstruct PortfolioStateSnapshot from a dict (with date/datetime conversion).

    Chunk F: Version-aware + defensive loading.
    - Detects snapshot_version (defaults to "1.0" for legacy records).
    - Explicitly supplies defaults for Phase 2 intelligence fields when absent
      (v1.0 snapshots or partial records). This guarantees that both v1.0 and
      v1.1+ records load without error and produce valid dataclass instances.
    - Strips unknown future keys to avoid **kwargs TypeError on forward-compat loads.
    - v1.1+ records will carry tactical_action, signal_stability_score,
      basic_rebalance_recommendation, and intelligence_provenance.
    """
    version = str(data.get("snapshot_version", "1.0"))

    # Defensive injection of Phase 2 optional fields (for v1.0 JSONL records)
    # These have defaults in the dataclass, but explicit setdefault makes the
    # contract visible and protects against any dict construction quirks.
    data.setdefault("tactical_action", None)
    data.setdefault("signal_stability_score", None)
    data.setdefault("basic_rebalance_recommendation", None)
    data.setdefault("intelligence_provenance", None)

    # Convert top-level dates
    if "as_of_date" in data and isinstance(data["as_of_date"], str):
        data["as_of_date"] = date.fromisoformat(data["as_of_date"])
    if "generated_at" in data and isinstance(data["generated_at"], str):
        data["generated_at"] = datetime.fromisoformat(data["generated_at"])

    # Convert holdings
    holdings = []
    for h in data.get("holdings", []):
        if "acquisition_date" in h and isinstance(h["acquisition_date"], str):
            h["acquisition_date"] = date.fromisoformat(h["acquisition_date"])
        holdings.append(HoldingSnapshot(**h))
    data["holdings"] = holdings

    # Filter to only known dataclass fields (forward compatibility: ignore future keys)
    known = {f.name for f in dc_fields(PortfolioStateSnapshot)}
    clean_data = {k: v for k, v in data.items() if k in known}

    snap = PortfolioStateSnapshot(**clean_data)

    # The snapshot_version on the instance tells callers which "era" this record came from.
    # (No branching logic here — just graceful materialization.)
    return snap


def _get_snapshot_path(base_path: str, portfolio_id: str) -> Path:
    """Deterministic per-portfolio JSONL file path."""
    base = Path(base_path)
    return base / f"{portfolio_id}_snapshots.jsonl"


def save_snapshot(snapshot: PortfolioStateSnapshot, base_path: str) -> str:
    """
    Append a single snapshot to the portfolio's JSONL file.
    Creates the directory structure if it does not exist.

    Chunk F note: When snapshot_version == "1.1", the record includes
    tactical_action / signal_stability_score / basic_rebalance_recommendation
    plus intelligence_provenance for traceability. No schema migration is
    performed here — this is append-only with graceful multi-version reads.
    """
    path = _get_snapshot_path(base_path, snapshot.portfolio_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Lightweight v1.1 hygiene marker (for human inspection of the JSONL)
    # The actual fields come from the snapshot itself.
    if getattr(snapshot, "snapshot_version", "1.0") == "1.1":
        # v1.1 enriched snapshot being persisted
        pass

    with open(path, "a", encoding="utf-8") as f:
        f.write(_serialize_snapshot(snapshot))

    return str(path)


def load_latest_snapshot(portfolio_id: str, base_path: str) -> Optional[PortfolioStateSnapshot]:
    """
    Load the most recent snapshot for the given portfolio_id.
    Returns None if no snapshots exist.
    For append-only files, we scan and keep the last successfully parsed snapshot
    to guarantee we get the most recently appended record (even if timestamps match).
    """
    path = _get_snapshot_path(base_path, portfolio_id)
    if not path.exists():
        return None

    latest: Optional[PortfolioStateSnapshot] = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                snap = _deserialize_snapshot(data)
                latest = snap  # last one wins
            except Exception:
                # skip malformed
                continue

    return latest


def load_snapshot_history(
    portfolio_id: str, base_path: str, limit: Optional[int] = None
) -> List[PortfolioStateSnapshot]:
    """
    Load historical snapshots for a portfolio (most recent first).
    Skips malformed lines gracefully.
    """
    path = _get_snapshot_path(base_path, portfolio_id)
    if not path.exists():
        return []

    snapshots: List[PortfolioStateSnapshot] = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                snap = _deserialize_snapshot(data)
                snapshots.append(snap)
            except Exception:
                # Malformed line – skip for robustness (Phase 1 simple logging)
                # In a real system this would go to a proper logger
                continue

    # Most recent first.
    # Sort by (as_of_date, generated_at) so that for same as_of_date, later generated wins.
    snapshots.sort(
        key=lambda s: (s.as_of_date, getattr(s, "generated_at", None) or datetime.min),
        reverse=True,
    )

    if limit is not None:
        snapshots = snapshots[:limit]

    return snapshots


# =============================================================================
# Phase 2 – Chunk F: Version-aware loader helper
# =============================================================================

def load_latest_snapshot_v2(portfolio_id: str, base_path: str) -> Optional[PortfolioStateSnapshot]:
    """
    Version-aware loader (Chunk F).

    Explicit entry point for loading snapshots that may be v1.0 or v1.1+.

    - Delegates to the robust _deserialize_snapshot which:
        * Detects snapshot_version (falls back to "1.0")
        * Supplies safe defaults for all Phase 2 intelligence + provenance fields
        * Strips unknown future keys for forward compatibility
    - v1.0 snapshots load cleanly with intelligence_* fields = None and
      snapshot_version="1.0" (or whatever was stored).
    - v1.1+ snapshots load with full tactical_action, signal_stability_score,
      basic_rebalance_recommendation, and intelligence_provenance intact.

    This provides the "graceful forward compatibility" required without any
    migration engine. Existing load_latest_snapshot remains available for
    backward compatibility of call sites.

    Returns None if no snapshots exist for the portfolio.
    """
    # The underlying load_latest_snapshot already uses the improved
    # _deserialize_snapshot, so v2 is primarily the documented, intentional
    # version-aware surface. Future chunks may add light branching or
    # returned metadata here.
    return load_latest_snapshot(portfolio_id, base_path)
