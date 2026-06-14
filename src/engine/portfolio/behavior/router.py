"""
Portfolio Router & State Isolation (v0.2)

Thin helper for managing isolated behavioral containers per portfolio slot.
Session-scoped only. No persistence beyond optional export.

Each slot holds a complete, independent behavioral context for the Companion:
- behavioral_state (NEUTRAL / CALMING / CHALLENGING)
- behavior_event_log (list of events for Memory Graph)
- active_conversational_tier
- full FriendProfile (as dict for serialization)
- max_dd / horizon for summaries (derived or stored)

All mutators are pure with respect to st.session_state.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from .events import get_events, capture_event
from ..friend_profile import FriendProfile, create_example_friend_profile


DEFAULT_SLOTS = [
    {
        "id": "P001_GROWTH",
        "name": "Core Retirement Nest Egg",
        "horizon": "12-Month Strategic Marathon",
        "max_dd": "15%",
    },
    {
        "id": "P002_PRESERVATION",
        "name": "Growth Satellite",
        "horizon": "12-Month Strategic Marathon",
        "max_dd": "15%",
    },
    {
        "id": "P003_INCOME",
        "name": "Income Anchor",
        "horizon": "12-Month Strategic Marathon",
        "max_dd": "10%",
    },
]


def _default_profile_for_slot(slot_id: str, slot_name: str) -> Dict[str, Any]:
    """Create a default FriendProfile dict for the slot."""
    profile = create_example_friend_profile(profile_id=f"{slot_id}_friend")
    # Customize slightly per slot for demo variety (still session-only)
    if "INCOME" in slot_id:
        profile = profile._replace(
            primary_goals=["moderate_income", "capital_preservation"],
            risk_constraints={"max_drawdown_pct": 10.0},
        )
    elif "PRESERVATION" in slot_id:
        profile = profile._replace(
            risk_constraints={"max_drawdown_pct": 12.0},
        )
    return profile.to_dict() if hasattr(profile, "to_dict") else {
        "profile_id": profile.profile_id,
        "personality_type": profile.personality_type,
        "primary_goals": profile.primary_goals,
        "risk_constraints": profile.risk_constraints,
        "sector_caps": profile.sector_caps,
        "ticker_caps": profile.ticker_caps,
        "behavioral_tendencies": profile.behavioral_tendencies,
        "communication_preference": profile.communication_preference,
        "free_text_notes": profile.free_text_notes,
        "created_at": str(profile.created_at),
        "provenance": profile.provenance,
    }


def initialize_portfolio_registry() -> None:
    """Initialize (or reset) the per-portfolio behavioral registry in session state."""
    if "portfolio_behavioral_registry" not in st.session_state:
        registry: Dict[str, Dict[str, Any]] = {}
        for slot in DEFAULT_SLOTS:
            registry[slot["id"]] = {
                "name": slot["name"],
                "state": "NEUTRAL",
                "events": [],
                "tier": 1,
                "max_dd": slot["max_dd"],
                "horizon": slot["horizon"],
                "profile": _default_profile_for_slot(slot["id"], slot["name"]),
            }
        st.session_state["portfolio_behavioral_registry"] = registry

    # Ensure current active slot keys exist in session for Friend surfaces
    if "active_portfolio_slot" not in st.session_state:
        st.session_state["active_portfolio_slot"] = "P001_GROWTH"

    # Bootstrap current session keys from registry if missing
    active = st.session_state["active_portfolio_slot"]
    reg = st.session_state["portfolio_behavioral_registry"].get(active, {})
    if "behavioral_state" not in st.session_state:
        st.session_state["behavioral_state"] = reg.get("state", "NEUTRAL")
    if "behavioral_events" not in st.session_state:
        st.session_state["behavioral_events"] = reg.get("events", [])
    if "active_conversational_tier" not in st.session_state:
        st.session_state["active_conversational_tier"] = reg.get("tier", 1)
    if "friend_profile" not in st.session_state:
        # Reconstruct minimal FriendProfile-like for current surfaces
        prof = reg.get("profile", {})
        st.session_state["friend_profile"] = create_example_friend_profile(
            profile_id=prof.get("profile_id", f"{active}_friend")
        )


def get_active_slot_id() -> str:
    return st.session_state.get("active_portfolio_slot", "P001_GROWTH")


def get_slot_display_name(slot_id: str) -> str:
    reg = st.session_state.get("portfolio_behavioral_registry", {})
    return reg.get(slot_id, {}).get("name", slot_id)


def get_slot_index(slot_id: str) -> int:
    reg = st.session_state.get("portfolio_behavioral_registry", {})
    ids = list(reg.keys())
    try:
        return ids.index(slot_id) + 1
    except ValueError:
        return 1


def get_total_slots() -> int:
    return len(st.session_state.get("portfolio_behavioral_registry", {}))


def write_current_behavioral_to_registry(slot_id: Optional[str] = None) -> None:
    """Persist the live session behavioral keys back into the registry for the slot."""
    if slot_id is None:
        slot_id = get_active_slot_id()

    reg = st.session_state.get("portfolio_behavioral_registry", {})
    if slot_id not in reg:
        return

    reg[slot_id]["state"] = st.session_state.get("behavioral_state", "NEUTRAL")
    reg[slot_id]["events"] = st.session_state.get("behavioral_events", [])
    reg[slot_id]["tier"] = st.session_state.get("active_conversational_tier", 1)
    # Store the profile as dict for round-tripping
    current_prof = st.session_state.get("friend_profile")
    if current_prof is not None:
        if hasattr(current_prof, "to_dict"):
            reg[slot_id]["profile"] = current_prof.to_dict()
        elif isinstance(current_prof, dict):
            reg[slot_id]["profile"] = current_prof
    st.session_state["portfolio_behavioral_registry"] = reg


def restore_behavioral_from_registry(slot_id: str) -> None:
    """Load behavioral context for the given slot into live session keys."""
    reg = st.session_state.get("portfolio_behavioral_registry", {})
    slot = reg.get(slot_id, {})

    st.session_state["behavioral_state"] = slot.get("state", "NEUTRAL")
    st.session_state["behavioral_events"] = slot.get("events", [])
    st.session_state["active_conversational_tier"] = slot.get("tier", 1)

    prof_dict = slot.get("profile", {})
    # Re-hydrate a FriendProfile for the surfaces that expect the dataclass
    try:
        st.session_state["friend_profile"] = create_example_friend_profile(
            profile_id=prof_dict.get("profile_id", f"{slot_id}_friend")
        )
        # Overlay key fields from stored dict for display accuracy
        if "personality_type" in prof_dict:
            # We keep the object but surfaces read from it; for v0.2 we accept the base + registry values
            pass
    except Exception:
        st.session_state["friend_profile"] = create_example_friend_profile(
            profile_id=f"{slot_id}_friend"
        )


def switch_to_slot(new_slot_id: str) -> None:
    """Full behavioral context switch with write-back + teardown."""
    if new_slot_id == get_active_slot_id():
        return

    # 1. Write current live state back
    write_current_behavioral_to_registry(get_active_slot_id())

    # 2. Update active slot
    st.session_state["active_portfolio_slot"] = new_slot_id

    # 3. Restore the new context into live session keys
    restore_behavioral_from_registry(new_slot_id)

    # 4. Global Unfiltered View enforcement (if active, force neutral for the new slot too)
    if st.session_state.get("unfiltered_view", False):
        st.session_state["behavioral_state"] = "NEUTRAL"

    # 5. Full surface teardown
    st.rerun()


def get_portfolio_summary_for_active() -> Dict[str, str]:
    """Light data for the Portfolio Summary line above Hero Band."""
    slot_id = get_active_slot_id()
    reg = st.session_state.get("portfolio_behavioral_registry", {}).get(slot_id, {})
    return {
        "name": reg.get("name", slot_id),
        "horizon": reg.get("horizon", "12-Month Strategic Marathon"),
        "max_dd": reg.get("max_dd", "15%"),
    }


def export_registry_as_json() -> str:
    """Optional affordance for user to export their Buddy states (v0.2)."""
    import json
    reg = st.session_state.get("portfolio_behavioral_registry", {})
    # Make it pretty and self-describing
    payload = {
        "version": "portfolio_router_v0.2",
        "buddy": "David",
        "slots": reg,
    }
    return json.dumps(payload, indent=2, default=str)


def force_neutral_all_slots() -> None:
    """Global enforcement for Unfiltered View: collapse every slot to NEUTRAL."""
    reg = st.session_state.get("portfolio_behavioral_registry", {})
    for sid in reg:
        reg[sid]["state"] = "NEUTRAL"
        reg[sid]["events"] = []  # optional: clear interpretation on global unfilter
    st.session_state["portfolio_behavioral_registry"] = reg
    st.session_state["behavioral_state"] = "NEUTRAL"
    st.session_state["behavioral_events"] = []
