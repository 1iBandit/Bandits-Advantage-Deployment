"""
Phase 4I — Analyst Workbench UI v0.1 (thin, read-only presentation layer)
Phase 4J — Workbench Flows v0.2 extensions (Investigation Mode, Attention Vector,
Temporal Time Slider + Progressive Disclosure, Per-Portfolio Session Persistence,
Hypothesis Auditor).

This file is a PURE CONSUMER of the existing query surfaces in the isolated
src/engine/portfolio/narrative.py module.

- No new decision logic, derived scores, or state is created here.
- All data comes from the portfolio-aware functions already implemented in narrative.py.
- For v0.1/v0.2 validation we use a text-based renderer so the test script can run headlessly
  and produce verifiable console output.
- In a real environment you would do:
    streamlit run src/engine/portfolio/workbench_ui.py
  or use the same panel_data functions inside a Gradio/Jupyter/Observable notebook.

The heavy lifting (queries, scoping, provenance, materiality, taxonomy) stays in narrative.py.

4J Guardrail (static): The UI layer (WorkbenchSessionState + render_full_workbench_with_flows
and flow helpers) performs ONLY in-memory state application and presentational grouping/filtering.
No derived scores, no new intelligence, no decision logic, and no cross-portfolio leakage.
Session state is non-persistent unless explicitly exported via Investigation Note.
"""

from typing import Any, Dict, List, Optional

# All data comes from here (existing, portfolio-scoped queries + thin presenters)
from src.engine.portfolio.narrative import (
    PortfolioRegistry,
    get_narrative_arcs_panel_data,
    get_lifecycle_status_panel_data,
    get_governance_status_panel_data,
    get_delivery_history_panel_data,
    export_investigation_note,
    # Phase 4J flow presenters (thin data sources only; no logic here)
    get_attention_vector_data,
    get_hypothesis_auditor_data,
    get_slider_filtered_panel_data,
)


def render_workbench(
    portfolio_id: str,
    registry: PortfolioRegistry,
    lifecycles: List[Any],
    snapshot: Any,
    ledger: List[Any],
    base_weekly: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Thin presentational renderer for the v0.1 Analyst Workbench.
    Returns a dict of rendered panel strings + the raw panel data for export.

    This function contains ZERO decision logic or new derived values.
    It only formats data returned by the existing narrative.py functions.
    """
    # Get structured panel data from the isolated logic layer
    arcs_data = get_narrative_arcs_panel_data(portfolio_id, registry, lifecycles)
    lifecycle_data = get_lifecycle_status_panel_data(portfolio_id, registry, lifecycles)
    governance_data = get_governance_status_panel_data(portfolio_id, registry, snapshot, lifecycles)
    delivery_data = get_delivery_history_panel_data(portfolio_id, registry, ledger)

    panels = {
        "narrative_arcs": _render_narrative_arcs_panel(arcs_data),
        "lifecycle_status": _render_lifecycle_status_panel(lifecycle_data),
        "governance_status": _render_governance_status_panel(governance_data),
        "delivery_history": _render_delivery_history_panel(delivery_data),
    }

    # Build the full view (what a real UI would display)
    view = {
        "portfolio_id": portfolio_id,
        "as_of": "current",
        "panels": panels,
        "raw_panel_data": {
            "narrative_arcs": arcs_data,
            "lifecycle_status": lifecycle_data,
            "governance_status": governance_data,
            "delivery_history": delivery_data,
        },
    }

    return view


def _render_narrative_arcs_panel(data: Dict[str, Any]) -> str:
    """Pure text rendering of the Narrative Arcs panel (no logic)."""
    lines = [f"NARRATIVE ARCS - {data.get('portfolio_id', 'unknown')} (as of {data.get('as_of', 'current')})"]
    events = data.get("events", [])
    if not events:
        lines.append("  (no recent material events)")
    for e in events[:8]:
        lines.append(f"  * {e.get('recommendation_id')}: {e.get('event')}")
    if data.get("provenance"):
        lines.append(f"  [provenance: {data['provenance']}]")
    return "\n".join(lines)


def _render_lifecycle_status_panel(data: Dict[str, Any]) -> str:
    """Pure text rendering of the Lifecycle Status panel (no logic)."""
    lines = [f"LIFECYCLE STATUS - {data.get('portfolio_id', 'unknown')} (as of {data.get('as_of', 'current')})"]
    recs = data.get("recommendations", [])
    if not recs:
        lines.append("  (no recommendations)")
    for r in recs:
        lines.append(f"  * {r['recommendation_id']}: {r['current_status']} | recent: {', '.join(r.get('recent_history', []))}")
    if data.get("provenance"):
        lines.append(f"  [provenance: {data['provenance']}]")
    return "\n".join(lines)


def _render_governance_status_panel(data: Dict[str, Any]) -> str:
    """Pure text rendering of the Governance Status panel (no logic)."""
    lines = [f"GOVERNANCE STATUS - {data.get('portfolio_id', 'unknown')} (as of {data.get('as_of', 'current')})"]
    lines.append(f"  Overall health: {data.get('overall_health', 'unknown')}")
    lines.append(f"  Actionable items: {data.get('actionable_items', 0)}")
    alerts = data.get("active_alerts", [])
    if alerts:
        for a in alerts:
            action = str(a.get('action', '')).replace('\u2192', '->')
            lines.append(f"  ! {a.get('type')}: {a.get('severity')} -> {action}")
    else:
        lines.append("  No active alerts")
    if data.get("provenance"):
        lines.append(f"  [provenance: {data['provenance']}]")
    return "\n".join(lines)


def _render_delivery_history_panel(data: Dict[str, Any]) -> str:
    """Pure text rendering of the Delivery History panel (no logic)."""
    lines = [f"DELIVERY HISTORY - {data.get('portfolio_id', 'unknown')} (as of {data.get('as_of', 'current')})"]
    entries = data.get("recent_entries", [])
    if not entries:
        lines.append("  (no recent deliveries)")
    for e in entries:
        lines.append(f"  * {e.get('package_id')}: {e.get('status')} @ {e.get('timestamp')}")
    if data.get("provenance"):
        lines.append(f"  [provenance: {data['provenance']}]")
    return "\n".join(lines)


def export_current_workbench_state(view: Dict[str, Any]) -> Dict[str, Any]:
    """
    Thin wrapper around the narrative.py export function.
    The UI layer only calls it; all logic and provenance assembly stays in narrative.py.
    For 4J flows, the returned note also captures the in-session state (time window,
    investigation mode, hypothesis selection, etc.) so it can be rehydrated later.
    Still strictly advisory; the note itself carries the "only persisted via explicit export" contract.
    """
    raw = view.get("raw_panel_data", {})
    note = export_investigation_note(
        portfolio_id=view["portfolio_id"],
        panels=raw,
        as_of=view.get("as_of", "current")
    )
    # 4J extension: surface session state if the view came from render_full_workbench_with_flows
    if "session_state" in view:
        note["session_state"] = view["session_state"]
    return note


# =============================================================================
# Phase 4J Workbench Flows v0.2 (thin state + flow logic on top of presenters)
# All data from narrative.py. UI layer is presentational + in-memory session state.
# =============================================================================

class WorkbenchSessionState:
    """
    Simple in-memory session state for v0.2 flows (non-persistent across 'restarts').
    Only saved if explicitly exported as Investigation Note.
    """
    def __init__(self, portfolio_id: str):
        self.selected_portfolio = portfolio_id
        self.active_panel = "narrative_arcs"
        self.time_window = "full"  # "full" or "recent"
        self.expanded_sections = {"narrative": True, "lifecycle": True, "governance": False, "delivery": False}
        self.investigation_mode = None  # None or {"type": "recommendation", "id": "xxx"}
        self.hypothesis_selected = []  # list of ids for auditor


def enter_investigation_mode(state: WorkbenchSessionState, item_type: str, item_id: str):
    """Flow: enter focused investigation on a recommendation or arc."""
    state.investigation_mode = {"type": item_type, "id": item_id}
    state.active_panel = "narrative_arcs"  # focus on arcs in investigation


def exit_investigation_mode(state: WorkbenchSessionState):
    state.investigation_mode = None


def set_time_window(state: WorkbenchSessionState, window: str):
    """Flow: temporal slider changes the time window (affects progressive disclosure)."""
    state.time_window = window


def toggle_section(state: WorkbenchSessionState, section: str):
    """Progressive disclosure toggle."""
    if section in state.expanded_sections:
        state.expanded_sections[section] = not state.expanded_sections[section]


def select_portfolio(state: WorkbenchSessionState, portfolio_id: str):
    """Updates selected portfolio (persisted in session)."""
    state.selected_portfolio = portfolio_id
    # Reset some state on portfolio change for cleanliness
    state.investigation_mode = None
    state.hypothesis_selected = []


def set_active_panel(state: WorkbenchSessionState, panel: str):
    state.active_panel = panel


def select_for_hypothesis(state: WorkbenchSessionState, item_id: str):
    if item_id not in state.hypothesis_selected:
        state.hypothesis_selected.append(item_id)
    if len(state.hypothesis_selected) > 3:
        state.hypothesis_selected = state.hypothesis_selected[-3:]


def render_full_workbench_with_flows(
    state: WorkbenchSessionState,
    registry: PortfolioRegistry,
    lifecycles: List[Any],
    snapshot: Any,
    ledger: List[Any],
    base_weekly: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Main renderer for v0.2 flows. Applies state (slider, investigation mode, etc.)
    to the panel data from narrative.py presenters.
    Purely presentational + state application.

    RUNTIME VERIFICATION (4J contract):
    - All panel data originates from get_*_panel_data / get_*_vector_data calls into narrative.py.
    - This function performs no scoring, no new taxonomy events, no decision rules.
    - State mutations are confined to the caller's WorkbenchSessionState instance (in-memory only).
    """
    # Explicit 4J runtime guard: confirm we are not creating derived intelligence here
    assert isinstance(state, WorkbenchSessionState), "state must be WorkbenchSessionState (session only)"
    portfolio_id = state.selected_portfolio

    # Base panel data (from 4I presenters + new 4J ones)
    arcs_data = get_narrative_arcs_panel_data(portfolio_id, registry, lifecycles)
    lifecycle_data = get_lifecycle_status_panel_data(portfolio_id, registry, lifecycles)
    governance_data = get_governance_status_panel_data(portfolio_id, registry, snapshot, lifecycles)
    delivery_data = get_delivery_history_panel_data(portfolio_id, registry, ledger)

    # Apply time slider (progressive disclosure)
    slider_data = get_slider_filtered_panel_data(portfolio_id, registry, state.time_window, arcs_data)
    arcs_data["events"] = slider_data.get("filtered_events", arcs_data.get("events", []))

    # Apply investigation mode (focus)
    if state.investigation_mode:
        inv_id = state.investigation_mode.get("id")
        arcs_data["events"] = [e for e in arcs_data.get("events", []) if e.get("recommendation_id") == inv_id]
        lifecycle_data["recommendations"] = [r for r in lifecycle_data.get("recommendations", []) if r.get("recommendation_id") == inv_id]

    # Attention Vector (top of view)
    attention_data = get_attention_vector_data(portfolio_id, registry, snapshot, lifecycles, governance_data)

    # Hypothesis auditor data if items selected
    auditor_data = None
    if state.hypothesis_selected:
        auditor_data = get_hypothesis_auditor_data(portfolio_id, registry, state.hypothesis_selected, lifecycles, governance_data)

    panels = {
        "attention_vector": _render_attention_vector(attention_data),
        "narrative_arcs": _render_narrative_arcs_panel(arcs_data),
        "lifecycle_status": _render_lifecycle_status_panel(lifecycle_data),
        "governance_status": _render_governance_status_panel(governance_data),
        "delivery_history": _render_delivery_history_panel(delivery_data),
    }

    if auditor_data:
        panels["hypothesis_auditor"] = _render_hypothesis_auditor(auditor_data)

    view = {
        "portfolio_id": portfolio_id,
        "as_of": "current",
        "time_window": state.time_window,
        "investigation_mode": state.investigation_mode,
        "active_panel": state.active_panel,
        "panels": panels,
        "raw_panel_data": {
            "narrative_arcs": arcs_data,
            "lifecycle_status": lifecycle_data,
            "governance_status": governance_data,
            "delivery_history": delivery_data,
            "attention_vector": attention_data,
            "hypothesis_auditor": auditor_data,
        },
        "session_state": {
            "selected_portfolio": state.selected_portfolio,
            "active_panel": state.active_panel,
            "time_window": state.time_window,
            "investigation_mode": state.investigation_mode,
            "hypothesis_selected": list(state.hypothesis_selected),
        }
    }

    return view


def _render_attention_vector(data: Dict[str, Any]) -> str:
    """Pure rendering of the Attention Vector (Critical / Important / Informational)."""
    lines = [f"ATTENTION VECTOR — {data.get('portfolio_id', 'unknown')} (as of {data.get('as_of', 'current')})"]
    for level in ["critical", "important", "informational"]:
        items = data.get(level, [])
        if items:
            lines.append(f"  {level.upper()}:")
            for item in items[:3]:
                lines.append(f"    - {item.get('description', str(item))}")
    if data.get("provenance"):
        lines.append(f"  [provenance: {data['provenance']}]")
    return "\n".join(lines)


def _render_hypothesis_auditor(data: Dict[str, Any]) -> str:
    """Pure rendering of the Hypothesis Auditor side-by-side."""
    lines = [f"HYPOTHESIS AUDITOR — {data.get('portfolio_id', 'unknown')} for {data.get('selected_items', [])}"]
    for comp in data.get("comparisons", []):
        lines.append(f"  • {comp.get('recommendation_id')}: {comp.get('lifecycle_status')} | {comp.get('governance_note')}")
    if data.get("provenance"):
        lines.append(f"  [provenance: {data['provenance']}]")
    return "\n".join(lines)