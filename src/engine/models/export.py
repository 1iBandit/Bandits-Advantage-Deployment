"""
Export result models (Phase 3 v1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ExportResult:
    """
    Lightweight result returned by the export step.

    Contains information about what was successfully written and any
    non-fatal errors encountered.
    """
    success: bool
    scorecard_path: Optional[str] = None
    history_path: Optional[str] = None
    num_rows: int = 0
    errors: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "SUCCESS" if self.success else "PARTIAL/FAILED"
        parts = [f"{status} - {self.num_rows} rows"]
        if self.scorecard_path:
            parts.append(f"Scorecard: {self.scorecard_path}")
        if self.history_path:
            parts.append(f"History: {self.history_path}")
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        return " | ".join(parts)
