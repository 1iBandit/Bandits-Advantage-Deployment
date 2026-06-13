"""
History_Archive writer (Phase 3 v1).

Writes long-term analytical history in Parquet format for efficient storage
and future querying / calibration work.

Design goals for v1:
- Robust append semantics (safe to call repeatedly).
- Consistent schema using ScorecardRow.to_dict().
- Adds tracking columns: written_at, run_id (when available).
- Graceful handling of first write (file does not exist yet).
- Defensive error handling (caller in export.py already catches exceptions).

The archive is intended as an append-only analytical store.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd

from engine.models.scorecard import ScorecardRow


logger = logging.getLogger(__name__)


def append(
    rows: List[ScorecardRow],
    output_path: str | Path,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Append ScorecardRow data to the long-term History Archive (Parquet).

    If the file does not exist, it will be created with the appropriate schema.
    If it exists, new rows are concatenated and the file is overwritten
    (standard safe append pattern for analytical Parquet files in v1).

    Tracking columns added:
    - written_at: ISO timestamp of when this batch was written.
    - run_id: from metadata if present.

    Args:
        rows: List of ScorecardRow objects to archive.
        output_path: Path to the Parquet file (e.g. Output/History_Archive.parquet).
        metadata: Optional metadata dict (run_id, as_of, scoring_config, etc.).
    """
    if not rows:
        return

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert rows using the stable to_dict() for consistent schema
    new_df = pd.DataFrame([row.to_dict() for row in rows])

    # Add tracking columns
    new_df["written_at"] = datetime.utcnow().isoformat()
    if metadata and "run_id" in metadata:
        new_df["run_id"] = metadata["run_id"]
    else:
        new_df["run_id"] = None

    # Reorder columns so tracking columns come first (nicer for inspection)
    cols = ["written_at", "run_id"] + [c for c in new_df.columns if c not in ("written_at", "run_id")]
    new_df = new_df[cols]

    # Try to write Parquet with best available engine
    engines_to_try = ["pyarrow", "fastparquet", None]  # None lets pandas choose

    written = False
    last_error = None

    for engine in engines_to_try:
        try:
            if output_path.exists():
                existing = pd.read_parquet(output_path)
                # Align columns
                for col in set(new_df.columns) - set(existing.columns):
                    existing[col] = None
                for col in set(existing.columns) - set(new_df.columns):
                    new_df[col] = None

                combined = pd.concat([existing, new_df], ignore_index=True)
                combined.to_parquet(output_path, index=False, engine=engine)
            else:
                new_df.to_parquet(output_path, index=False, engine=engine)

            logger.info(f"Appended {len(new_df)} rows to history archive: {output_path} (engine={engine or 'auto'})")
            written = True
            break
        except Exception as e:
            last_error = e
            continue

    if not written:
        logger.warning(f"Failed to write history archive to {output_path}: {last_error}")
        # As a last resort, write a CSV version so data is not lost
        csv_path = output_path.with_suffix(".csv")
        try:
            if csv_path.exists():
                existing_csv = pd.read_csv(csv_path)
                combined = pd.concat([existing_csv, new_df], ignore_index=True)
                combined.to_csv(csv_path, index=False)
            else:
                new_df.to_csv(csv_path, index=False)
            logger.info(f"Fell back to CSV history archive: {csv_path}")
        except Exception as e:
            logger.error(f"Completely failed to write history (Parquet and CSV): {e}")
