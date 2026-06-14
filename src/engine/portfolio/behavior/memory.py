"""
Relationship Memory Graph v0.1 (session-scoped, single node type for CALMING).

Records panic_pattern nodes for this micro-chunk.

All in-memory. User agency preserved (future view/delete).

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class PanicPatternNode:
    triggers: List[str]
    behaviors: List[str]
    emotional_inference: str  # e.g. "anxiety_spike"
    stabilization_response: str  # e.g. "calming_flow_v0"
    outcome: Optional[str] = None  # e.g. "no_panic_sale"
    timestamp: datetime = field(default_factory=datetime.now)


def add_panic_pattern(node: PanicPatternNode) -> None:
    """Add a panic_pattern node to the session memory graph."""
    import streamlit as st
    if "panic_pattern_nodes" not in st.session_state:
        st.session_state["panic_pattern_nodes"] = []
    st.session_state["panic_pattern_nodes"].append(node)


def get_current_panic_pattern() -> Optional[PanicPatternNode]:
    """Return the most recent panic_pattern node, if any."""
    import streamlit as st
    nodes = st.session_state.get("panic_pattern_nodes", [])
    if nodes:
        return nodes[-1]
    return None
