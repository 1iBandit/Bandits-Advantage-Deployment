"""
Behavioral layer for the Interactive Core Engine (Phase 4K+).

Session-scoped for v0.1. All logic is thin and isolated from decision layer.

Re-exports the minimal for the CALMING micro-chunk.
"""

from .events import (
    BehavioralEvent,
    capture_event,
    get_events,
    count_events_in_window,
)
from .memory import (
    PanicPatternNode,
    add_panic_pattern,
    get_current_panic_pattern,
)
from .state_engine import infer_state

__all__ = [
    "BehavioralEvent",
    "capture_event",
    "get_events",
    "count_events_in_window",
    "PanicPatternNode",
    "add_panic_pattern",
    "get_current_panic_pattern",
    "infer_state",
]
