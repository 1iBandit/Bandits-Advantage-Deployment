"""
Export step (Phase 3 v1 - minimal).

Responsibilities:
- Accept EngineOutput or raw List[ScorecardRow].
- Extract rows and metadata.
- Write Scorecard.xlsx (primary focus for v1).
- Optionally write to History Archive (opt-in).
- Be defensive with errors.
- Return a small ExportResult with paths and status.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd

from engine.models.core import EngineOutput
from engine.models.scorecard import ScorecardRow
from engine.models.export import ExportResult
from engine.io import excel_writer
from engine.io import history_writer


def export(
    data: EngineOutput | List[ScorecardRow] | dict,
    config: Any = None,
) -> ExportResult:
    """
    Minimal v1 export step.

    Writes the processed scorecard data to disk.

    For v1 the primary output is Scorecard.xlsx. History writing is opt-in
    via config (e.g. config.get("write_history", False)).
    """
    result = ExportResult(success=True)
    rows: List[ScorecardRow] = _extract_rows(data)

    if not rows:
        result.success = False
        result.errors.append("No rows to export")
        return result

    result.num_rows = len(rows)

    # Determine output locations
    output_dir = _resolve_output_dir(config)
    scorecard_path = _resolve_scorecard_path(config, output_dir)
    history_path = _resolve_history_path(config, output_dir)

    # === Primary: Scorecard.xlsx ===
    try:
        excel_writer.write_scorecard(
            rows=rows,
            output_path=scorecard_path,
            metadata=_build_metadata(data, config),
        )
        result.scorecard_path = str(scorecard_path)
    except Exception as e:
        result.success = False
        result.errors.append(f"Excel writer failed: {e}")

    # === Optional: History Archive (opt-in for v1) ===
    write_history = False
    if isinstance(config, dict):
        write_history = config.get("write_history", False)
    elif hasattr(config, "get"):
        try:
            write_history = config.get("write_history", False)
        except Exception:
            pass

    if write_history:
        try:
            history_writer.append(
                rows=rows,
                output_path=history_path,
                metadata=_build_metadata(data, config),
            )
            result.history_path = str(history_path)
        except Exception as e:
            result.errors.append(f"History writer failed: {e}")
            # Do not flip success=False for history failure in v1

    if not result.scorecard_path:
        result.success = False

    return result


# =============================================================================
# Internal helpers (kept small and focused)
# =============================================================================

def _extract_rows(data: Any) -> List[ScorecardRow]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, ScorecardRow)]
    if isinstance(data, EngineOutput):
        if data.scorecard_rows:
            return data.scorecard_rows
        # Fallback: try to convert TickerScores if no scorecard_rows yet
        # (useful during transition)
        return []
    return []


def _resolve_output_dir(config: Any) -> Path:
    """Resolve output directory with sensible defaults."""
    if isinstance(config, dict):
        path = config.get("output_dir") or config.get("output_path")
        if path:
            return Path(path).parent if Path(path).suffix else Path(path)

    # Default: Output/ relative to current working directory
    default = Path.cwd() / "Output"
    default.mkdir(parents=True, exist_ok=True)
    return default


def _resolve_scorecard_path(config: Any, output_dir: Path) -> Path:
    if isinstance(config, dict):
        explicit = config.get("scorecard_path") or config.get("scorecard_file")
        if explicit:
            p = Path(explicit)
            return p if p.is_absolute() else output_dir / p.name

    # Default filename with date for safety
    filename = f"Scorecard_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return output_dir / filename


def _resolve_history_path(config: Any, output_dir: Path) -> Path:
    if isinstance(config, dict):
        explicit = config.get("history_path") or config.get("history_file")
        if explicit:
            p = Path(explicit)
            return p if p.is_absolute() else output_dir / p.name

    filename = "History_Archive.parquet"  # or .csv / .xlsx later
    return output_dir / filename


def _build_metadata(data: Any, config: Any) -> dict:
    meta: dict = {}
    if isinstance(data, EngineOutput):
        meta.update({
            "run_id": data.run_id,
            "as_of": data.as_of,
        })
        if data.metadata:
            meta["run_metadata"] = data.metadata

    if isinstance(config, dict):
        # Pass through any explicit metadata the caller wants
        if "metadata" in config:
            meta.update(config["metadata"])

    return meta
