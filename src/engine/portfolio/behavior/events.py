"""
Behavioral Event Stream (BES) – v0.1 (session-scoped).

Captures meaningful interaction signals for emotional/behavioral inference.

All data is in-memory per session for this micro-chunk. No persistence.

Ethical: No keystrokes, no text sentiment, no biometrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class BehavioralEvent:
    event_type: str
    timestamp: datetime
    context: Dict[str, Any] = field(default_factory=dict)


def capture_event(event_type: str, context: Optional[Dict[str, Any]] = None) -> None:
    """Append an event to the session stream."""
    import streamlit as st

    if "behavioral_events" not in st.session_state:
        st.session_state["behavioral_events"] = []

    event = BehavioralEvent(
        event_type=event_type,
        timestamp=datetime.now(),
        context=context or {},
    )
    st.session_state["behavioral_events"].append(event)


def get_events() -> List[BehavioralEvent]:
    """Return all captured events in the current session."""
    import streamlit as st
    return st.session_state.get("behavioral_events", [])


def count_events_in_window(
    event_type: str, events: List[BehavioralEvent], window: timedelta
) -> int:
    """Count events of a type within the time window from now."""
    cutoff = datetime.now() - window
    return sum(
        1 for e in events if e.event_type == event_type and e.timestamp >= cutoff
    )
