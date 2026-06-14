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
from .router import (
    initialize_portfolio_registry,
    get_active_slot_id,
    get_slot_display_name,
    get_slot_index,
    get_total_slots,
    write_current_behavioral_to_registry,
    restore_behavioral_from_registry,
    switch_to_slot,
    get_portfolio_summary_for_active,
    export_registry_as_json,
    force_neutral_all_slots,
)

__all__ = [
    "BehavioralEvent",
    "capture_event",
    "get_events",
    "count_events_in_window",
    "PanicPatternNode",
    "add_panic_pattern",
    "get_current_panic_pattern",
    "infer_state",
    # v0.2 Portfolio Router (behavioral isolation)
    "initialize_portfolio_registry",
    "get_active_slot_id",
    "get_slot_display_name",
    "get_slot_index",
    "get_total_slots",
    "write_current_behavioral_to_registry",
    "restore_behavioral_from_registry",
    "switch_to_slot",
    "get_portfolio_summary_for_active",
    "export_registry_as_json",
    "force_neutral_all_slots",
]
