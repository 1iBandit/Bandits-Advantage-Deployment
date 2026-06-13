"""
Excel writer for Scorecard.xlsx (Phase 3 v1 - minimal).

Focus:
- Write the core ScorecardRow data cleanly into a single sheet.
- No heavy formatting, styling, or multiple sheets yet.
- Accept List[ScorecardRow] + optional metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import pandas as pd

from engine.models.scorecard import ScorecardRow


def write_scorecard(
    rows: List[ScorecardRow],
    output_path: str | Path,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Minimal v1 writer.

    Writes the provided rows to a .xlsx file using pandas.
    Creates parent directories if they do not exist.
    """
    if not rows:
        return

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert dataclass list to DataFrame
    df = pd.DataFrame([_row_to_dict(r) for r in rows])

    # Write with a basic sheet name
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Scorecard", index=False)

        # Optional: write a small metadata sheet if provided
        if metadata:
            meta_df = pd.DataFrame(
                [{"key": k, "value": str(v)} for k, v in metadata.items()]
            )
            meta_df.to_excel(writer, sheet_name="RunInfo", index=False)


def _row_to_dict(row: ScorecardRow) -> dict[str, Any]:
    """Convert ScorecardRow to a flat dict for DataFrame export.
    Delegates to the stable to_dict() on the model for consistency.
    """
    return row.to_dict()
