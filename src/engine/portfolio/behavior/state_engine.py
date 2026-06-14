"""
Emotional State Inference Engine v0.1 – CALMING only for this micro-chunk.

Rule-based. No ML. Transparent and explainable.

"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from .events import BehavioralEvent, count_events_in_window


def infer_state(events: List[BehavioralEvent]) -> Optional[str]:
    """
    Infer CALMING state if user shows high checking behavior in down market.

    Returns "CALMING" or None.
    """
    checks = count_events_in_window("portfolio_check", events, timedelta(hours=24))
    projections = count_events_in_window("projection_view", events, timedelta(hours=24))
    hovers = count_events_in_window("hover_sell", events, timedelta(hours=24))

    if checks >= 5 and (projections >= 2 or hovers >= 1):
        return "CALMING"
    return None
