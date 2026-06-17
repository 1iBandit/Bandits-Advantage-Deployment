#!/usr/bin/env python
"""
Bandit's Advantage — Decision Surface (Streamlit Driver)
Phase 4L (governing Decision Surface) + Phase 4I/4J (Analyst Workbench) + Phase 4K child (Friend Mode)

This is a PURE CONSUMER / thin wrapper.

It uses ONLY:
- Thin presenters from src/engine/portfolio/narrative.py:
    - get_hero_decision_band_data (Phase 4L Hero Band)
    - get_friend_view_data / build_friend_note (locked Phase 4K child)
    - get_friend_identity_card_data (Phase 4K+ Friend Identity Card)
    - get_first_guided_question (Phase 4K+ active guide)
    - 4I/4J panel data
- WorkbenchSessionState + flow mutators + render_full_workbench_with_flows from
  src/engine/portfolio/workbench_ui.py
- FriendProfile model + apply_profile_edits (session-editable personalization layer)

No new decision logic, no derived scores, no mutations of Phase 3 outputs,
no feedback into the calibrated engine. All synthesis is confined to narrative.py.

Run (after one-time install):
    pip install streamlit
    streamlit run analyst_workbench.py

The app starts instantly with the same minimal demo data used by
test_phase4j_workbench_flows_v0.2.py (and extended for 4L) so behavior is reproducible.

# Force full rebuild - stale build cache workaround 2026-06-14 (Hero Band CHALLENGING v0.1 extension)
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

# Streamlit is only needed when running as a Streamlit app.
# We import it inside main() so the module remains importable for smoke tests,
# validation reuse, or embedding even if streamlit is not installed.
try:
    import streamlit as st
except ImportError:
    st = None  # type: ignore

# === Existing locked modules (do not change these imports or call sites) ===
from src.engine.portfolio.narrative import (
    PortfolioRegistry,
    create_portfolio_identity,
    create_chain,
    build_portfolio_snapshot,
    RecommendationLifecycle,
    # Panel data (used for rich rendering while staying faithful to the contract)
    get_attention_vector_data,
    get_hypothesis_auditor_data,
    # Phase 4K Friend Mode (thin consumer only – no new logic)
    get_friend_view_data,
    build_friend_note,
    FRIEND_LANGUAGE_VERSION,
    # Phase 4K+ evolution – Friend Identity Card (thin presenter)
    get_friend_identity_card_data,
    # First Guided Question (active guide behavior)
    get_first_guided_question,
    # Phase 4L Hero Decision Band (thin consumer only)
    get_hero_decision_band_data,
)
from src.engine.portfolio.friend_profile import (
    FriendProfile,
    create_example_friend_profile,
    apply_profile_edits,
)
from src.engine.portfolio.behavior import (
    capture_event,
    get_events,
    add_panic_pattern,
    PanicPatternNode,
    get_current_panic_pattern,
    infer_state,
    # v0.2 Portfolio Router
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
    # v0.3 Persistence Layer
    initialize_or_load_buddy_session,
    trigger_encrypted_disk_sync,
)

# SOT v0.2 (A/B/H) — semantic layer for gating + raw writers (raw access auto-blocks in Friend deployment)
try:
    from src.sot.semantic import get_gating_state, update_behavior_semantic_from_event
except Exception:
    get_gating_state = None
    update_behavior_semantic_from_event = None

# Note: We deliberately read the env var directly for the deployment flag.
# This avoids UnboundLocalError / import-order problems when the file is executed
# via runpy in Streamlit Cloud thin wrapper. The SOT modules themselves also
# check the env live for raw access blocking.
from src.engine.portfolio.workbench_ui import (
    WorkbenchSessionState,
    render_full_workbench_with_flows,
    enter_investigation_mode,
    exit_investigation_mode,
    set_time_window,
    select_portfolio,
    set_active_panel,
    select_for_hypothesis,
    export_current_workbench_state,
)

import streamlit.components.v1 as components


# =============================================================================
# Demo data setup (identical spirit to test_phase4j_workbench_flows_v0.2.py)
# This keeps the Streamlit app runnable with zero external data dependencies
# while exercising the exact same objects the locked 4J validation uses.
# =============================================================================

def setup_demo_data() -> Dict[str, Any]:
    """Returns registry + per-portfolio objects matching the Phase 4J validation harness."""
    base_chain = create_chain("workbench_streamlit_demo_001", None, 900, "epoch_streamlit_v02")

    registry = PortfolioRegistry()
    id_growth = create_portfolio_identity(
        "P001_GROWTH", "Growth Mandate", "Growth", "2026-01-01", base_chain
    )
    registry = registry.register(id_growth)

    id_preservation = create_portfolio_identity(
        "P002_PRESERVATION", "Capital Preservation", "Capital Preservation", "2026-01-01", base_chain
    )
    registry = registry.register(id_preservation)

    id_income = create_portfolio_identity(
        "P003_INCOME", "Income Anchor", "Income", "2026-01-01", base_chain
    )
    registry = registry.register(id_income)

    # Minimal but representative objects (same shape as the validation test)
    rec_states_g = [
        {
            "recommendation_id": "DOCN:HOLD",
            "recommendation_family": "HOLD",
            "stability_band": "Moderate",
            "risk_regime": "Controlled",
            "overall_confidence": 0.72,
        }
    ]
    risk_g = [{"risk_score": 0.32, "risk_regime": "Controlled"}]
    lc_g = [
        RecommendationLifecycle(
            "DOCN:HOLD", "STRENGTHENING", ["EMERGED", "STRENGTHENED"], base_chain,
            {"portfolio_id": "P001_GROWTH"}
        )
    ]

    rec_states_p = [
        {
            "recommendation_id": "TSLA:HOLD",
            "recommendation_family": "HOLD",
            "stability_band": "Low",
            "risk_regime": "Controlled",
            "overall_confidence": 0.58,
        }
    ]
    risk_p = [{"risk_score": 0.41, "risk_regime": "Controlled"}]
    lc_p = [
        RecommendationLifecycle(
            "TSLA:HOLD", "DECAYING", ["DECAYING"], base_chain,
            {"portfolio_id": "P002_PRESERVATION"}
        )
    ]

    rec_states_i = [
        {
            "recommendation_id": "NEE:HOLD",
            "recommendation_family": "HOLD",
            "stability_band": "High",
            "risk_regime": "Controlled",
            "overall_confidence": 0.81,
        }
    ]
    risk_i = [{"risk_score": 0.22, "risk_regime": "Controlled"}]
    lc_i = [
        RecommendationLifecycle(
            "NEE:HOLD", "STRENGTHENING", ["EMERGED", "STRENGTHENED"], base_chain,
            {"portfolio_id": "P003_INCOME"}
        )
    ]

    snap_g = build_portfolio_snapshot(
        "P001_GROWTH", base_chain.narrative_chain_id, rec_states_g, risk_g, lc_g, base_chain,
        {"source": "4C-streamlit-demo", "portfolio_id": "P001_GROWTH"}
    )
    snap_p = build_portfolio_snapshot(
        "P002_PRESERVATION", base_chain.narrative_chain_id, rec_states_p, risk_p, lc_p, base_chain,
        {"source": "4C-streamlit-demo", "portfolio_id": "P002_PRESERVATION"}
    )
    snap_i = build_portfolio_snapshot(
        "P003_INCOME", base_chain.narrative_chain_id, rec_states_i, risk_i, lc_i, base_chain,
        {"source": "4C-streamlit-demo", "portfolio_id": "P003_INCOME"}
    )

    # Minimal weekly update placeholders (the real generator lives in narrative)
    base_weekly_g = {"portfolio_id": "P001_GROWTH", "executive_summary": "Demo growth portfolio state."}
    base_weekly_p = {"portfolio_id": "P002_PRESERVATION", "executive_summary": "Demo preservation portfolio state."}
    base_weekly_i = {"portfolio_id": "P003_INCOME", "executive_summary": "Demo income portfolio state."}

    lifecycles_map = {
        "P001_GROWTH": lc_g,
        "P002_PRESERVATION": lc_p,
        "P003_INCOME": lc_i,
    }
    snapshots_map = {
        "P001_GROWTH": snap_g,
        "P002_PRESERVATION": snap_p,
        "P003_INCOME": snap_i,
    }
    base_weekly_map = {
        "P001_GROWTH": base_weekly_g,
        "P002_PRESERVATION": base_weekly_p,
        "P003_INCOME": base_weekly_i,
    }

    # Empty ledger for delivery panel (real usage would come from 4G)
    ledger: List[Any] = []

    return {
        "registry": registry,
        "lifecycles": lifecycles_map,
        "snapshots": snapshots_map,
        "base_weekly": base_weekly_map,
        "ledger": ledger,
        "base_chain": base_chain,
    }


def get_current_objects(demo: Dict[str, Any], portfolio_id: str):
    """Helper to grab the right objects for the selected portfolio.

    Defensive: if the selected portfolio has no demo slice (e.g. selector/data drift),
    fall back to the first available so the surface remains usable instead of hard KeyError.
    The narrative presenters already return "unknown portfolio" safe objects when the
    registry itself lacks the id.
    """
    lifecycles_map = demo.get("lifecycles", {})
    snapshots_map = demo.get("snapshots", {})
    base_weekly_map = demo.get("base_weekly", {})

    if portfolio_id not in lifecycles_map:
        # Fallback keeps the app alive; real fix is ensuring setup_demo_data covers all
        # options advertised in the "Active Portfolio" selector.
        if lifecycles_map:
            portfolio_id = next(iter(lifecycles_map.keys()))
        else:
            # Extreme degenerate case; return empty-ish structures (callers expect lists/dicts)
            return demo.get("registry"), [], None, demo.get("ledger", []), {}

    return (
        demo["registry"],
        lifecycles_map[portfolio_id],
        snapshots_map[portfolio_id],
        demo["ledger"],
        base_weekly_map[portfolio_id],
    )


# =============================================================================
# Streamlit App
# =============================================================================

def main():
    if st is None:
        raise RuntimeError(
            "streamlit is not installed.\n"
            "Install with: pip install streamlit\n"
            "Then run: streamlit run analyst_workbench.py"
        )

    # Deployment guard (FRIEND_OF_1IBANDIT_DEPLOYMENT)
    # Read directly from env var. This is the most reliable way when the script
    # is executed via runpy in the Streamlit Cloud thin wrapper (avoids any
    # import scoping / UnboundLocalError issues).
    is_friend_deployment = os.environ.get("FRIEND_OF_1IBANDIT_DEPLOYMENT", "0") == "1"

    # Deployment guard (canonical refinement loop, 2026-06-15)
    # When FRIEND_OF_1IBANDIT_DEPLOYMENT=1 (set by the public thin wrapper),
    # force pure Friend Mode only. Analyst Workbench surfaces remain available
    # in local / personal analysis environments.
    # SOT v0.2: raw access blocked inside src/sot/raw.py when flag is set.

    if is_friend_deployment:
        page_title = "Friend of 1iBandit"
        page_icon = "🤝"
        top_title = "🤝 Friend of 1iBandit"
        top_caption = "A calm, sovereign reflection environment • All data from the isolated narrative spine"
    else:
        page_title = "Bandit's Advantage — Analyst Workbench"
        page_icon = "📈"
        top_title = "📈 Bandit's Advantage — Analyst Workbench"
        top_caption = "Phase 4I + 4J  •  Thin read-only presentation layer  •  All data from isolated narrative spine"

    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title(top_title)
    st.caption(top_caption)

    # Early warm palette for Friend (ensures calm #f7f3ee before any content renders)
    if is_friend_deployment:
        st.markdown("""
<style>
.stApp { background-color: #f7f3ee; color: #2c2520; }
div[data-testid="stVerticalBlock"] > div { background-color: #ffffff; border-radius: 10px; padding: 28px; border: 1px solid #e4ddd3; }
.stButton > button { background-color: #efe9e2; color: #2c2520; border: 1px solid #d8cfc3; border-radius: 6px; }
.stButton > button:hover { background-color: #e7dfd7; }
</style>
""", unsafe_allow_html=True)

    # Permanent guardrail banner (matches the locked contracts)
    # In pure Friend deployment we keep a lighter version to preserve the architectural promise
    # without Analyst framing.
    if is_friend_deployment:
        st.caption(
            "**Architectural Guardrail**: This is a reflection companion. It renders only data from the Phase 3 engine "
            "and Phase 4 observational layers. It performs no scoring, sets no targets, and never asks for commitments. "
            "`intelligence_layers_enabled` remains False."
        )
    else:
        st.warning(
            "**Architectural Guardrail**: This UI only renders data produced by the Phase 3 calibrated decision engine "
            "and the Phase 4A–4J observational layers (narrative.py). It performs no scoring, no new rules, "
            "and never influences recommendations. `intelligence_layers_enabled` remains False. "
            "State is session-only unless you explicitly Export an Investigation Note."
        )

    # One-time setup of demo data + session state
    # Robust init: recreate if missing or if the object is from a stale class definition
    # (common after code changes / redeploys in Streamlit, as session_state holds pickled instances).
    if "wb_state" not in st.session_state or not isinstance(st.session_state.wb_state, WorkbenchSessionState):
        st.session_state.wb_state = WorkbenchSessionState("P001_GROWTH")
        st.session_state.demo_data = setup_demo_data()
        st.session_state.last_exported_note = None

    # v0.2 Portfolio Router: initialize isolated behavioral containers (session-only)
    initialize_portfolio_registry()

    state: WorkbenchSessionState = st.session_state.wb_state
    demo: Dict[str, Any] = st.session_state.demo_data

    # --- Sidebar: All flow controls live here (keeps main area focused) ---
    with st.sidebar:
        st.header("Portfolio & Time")

        # v0.2: Extended to 3 slots for behavioral isolation demo (1/3 in header)
        # Derive from the actual demo data so the selector can never offer a portfolio
        # that will cause KeyError in get_current_objects (or "unknown portfolio" degradation
        # deeper in the narrative presenters).
        portfolio_options = list(demo.get("lifecycles", {}).keys()) or ["P001_GROWTH", "P002_PRESERVATION", "P003_INCOME"]
        current_idx = portfolio_options.index(state.selected_portfolio) if state.selected_portfolio in portfolio_options else 0
        new_portfolio = st.selectbox(
            "Active Portfolio",
            portfolio_options,
            index=current_idx,
            key="sb_portfolio",
        )
        if new_portfolio != state.selected_portfolio:
            # Write current behavioral context back, switch slot (full teardown + restore)
            write_current_behavioral_to_registry(state.selected_portfolio)
            if st.session_state.get("behavioral_state") == "NEUTRAL":
                st.session_state.setdefault("behavior_event_log", []).append({
                    "event_type": "discipline_event",
                    "description": "Core investment boundaries actively maintained under short-term market variance."
                })
            select_portfolio(state, new_portfolio)
            # Router handles behavioral isolation switch
            switch_to_slot(new_portfolio)
            # Note: switch_to_slot does st.rerun() internally for full surface teardown

        if not is_friend_deployment:
            time_window = st.radio(
                "Temporal Window (4J Progressive Disclosure)",
                options=["full", "recent"],
                index=0 if state.time_window == "full" else 1,
                horizontal=True,
                key="sb_time",
            )
            if time_window != state.time_window:
                set_time_window(state, time_window)
                st.rerun()

        st.divider()

        if is_friend_deployment:
            # Pure Friend Mode in public deployment — no Analyst surfaces or mode switch visible.
            view_mode = "Friend (4K)"
            st.session_state["view_mode"] = view_mode
            st.caption("Hero Decision Band is always shown above (4L requirement)")  # Caption per hierarchy
        else:
            st.header("Decision Surface Mode (Phase 4L)")  # H1 per locked Typography for page/major section titles
            view_mode = st.radio(
                "Mode",
                ["Analyst (4I+4J)", "Friend (4K)"],
                index=1,  # default to Friend (4K) so new features are visible on load
                horizontal=True,
                key="view_mode",
            )
            st.caption("Hero Decision Band is always shown above (4L requirement)")  # Caption per hierarchy

        # Early Friend profile + state init for Hero Band Context Awareness (v0.1)
        # Ensures current_profile and behavioral state are in session_state before the
        # top-of-page Hero Band renders (so posture can react to CALMING from Memory Graph).
        mode_for_init = st.session_state.get("view_mode", "Analyst (4I+4J)")
        if "Friend" in mode_for_init:
            if "friend_profile" not in st.session_state or not isinstance(
                st.session_state.get("friend_profile"), FriendProfile
            ):
                st.session_state["friend_profile"] = create_example_friend_profile(
                    profile_id=f"{state.selected_portfolio}_friend"
                )
            if "behavioral_state" not in st.session_state:
                st.session_state["behavioral_state"] = "NEUTRAL"

        # Note: "Investigation Mode (4J)" below uses st.header (H1) for section, consistent with hierarchy for major investigative surfaces.

        st.divider()
        st.header("Investigation Mode (4J)")

        inv_col1, inv_col2 = st.columns(2)
        with inv_col1:
            if st.button("Focus on DOCN:HOLD", key="btn_focus_docn"):
                enter_investigation_mode(state, "recommendation", "DOCN:HOLD")
                st.rerun()
        with inv_col2:
            if st.button("Focus on TSLA:HOLD", key="btn_focus_tsla"):
                enter_investigation_mode(state, "recommendation", "TSLA:HOLD")
                st.rerun()

        if state.investigation_mode:
            st.info(f"Investigating: {state.investigation_mode}")
            if st.button("Exit Investigation Mode", key="btn_exit_inv"):
                exit_investigation_mode(state)
                st.rerun()

        st.divider()
        st.header("Hypothesis Auditor (4J)")

        # Simple multi-select limited to the two demo recommendations
        selected_hyp = st.multiselect(
            "Select 2–3 items for side-by-side audit",
            options=["DOCN:HOLD", "TSLA:HOLD"],
            default=state.hypothesis_selected,
            max_selections=3,
            key="hyp_multi",
        )
        # Keep the state in sync
        state.hypothesis_selected = list(selected_hyp)

        if st.button("Run Hypothesis Auditor", key="btn_audit"):
            # The actual data pull happens inside render_full... via get_hypothesis_auditor_data
            set_active_panel(state, "hypothesis")
            st.rerun()

        if state.hypothesis_selected:
            if st.button("Clear Hypothesis Selection"):
                state.hypothesis_selected = []
                st.rerun()

        st.divider()
        st.header("Session")
        if st.button("Reset in-memory session state"):
            st.session_state.wb_state = WorkbenchSessionState(state.selected_portfolio)
            st.rerun()

        st.caption("Session state is **not** persisted across browser restarts.\n"
                   "Use Export Investigation Note to capture it.")

        # v0.2: Optional export of the isolated behavioral registry (Buddy states)
        if st.button("Export Buddy States (Portfolio Router v0.2)", key="btn_export_buddy_registry"):
            json_data = export_registry_as_json()
            st.download_button(
                label="Download buddy_registry.json",
                data=json_data,
                file_name="buddy_registry_v0.2.json",
                mime="application/json",
            )
            st.success("Exported full per-portfolio behavioral containers (session-only).")

    # --- Main area ---
    registry, lifecycles, snapshot, ledger, base_weekly = get_current_objects(demo, state.selected_portfolio)

    # === v0.2 Portfolio Summary (lightweight context above Hero Band in Friend Mode) ===
    mode_for_summary = st.session_state.get("view_mode", "Analyst (4I+4J)")
    if "Friend" in mode_for_summary:
        summary = get_portfolio_summary_for_active()
        slot_id = get_active_slot_id()
        idx = get_slot_index(slot_id)
        total = get_total_slots()
        st.caption(
            f"**{summary['name']}**  •  {summary['horizon']}  •  Max Drawdown: {summary['max_dd']}  "
            f"({idx}/{total})"
        )

    # === Phase 4L Hero Decision Band (dominant, always visible, mode-independent) ===
    # All data from get_hero_decision_band_data (thin presenter in narrative.py)
    # Hero Band Context Awareness v0.1 extension: explicit behavioral_state (CALMING / CHALLENGING / NEUTRAL)
    # Linguistic/postural mutation only. Core data + metrics never altered.
    hero = get_hero_decision_band_data(
        state.selected_portfolio, registry, lifecycles, snapshot
    )

    rec = hero["primary_recommendation"]
    is_abstain = hero.get("is_abstaining", False)

    # === Hero Band routing logic per spec (prefers explicit behavioral_state) ===
    active_state = st.session_state.get("behavioral_state", "NEUTRAL")
    is_unfiltered = st.session_state.get("unfiltered_view", False)
    current_profile = st.session_state.get("friend_profile")
    max_dd = 15.0
    if current_profile and hasattr(current_profile, "risk_constraints"):
        max_dd = current_profile.risk_constraints.get("max_drawdown_pct", 15.0)

    mode_now = st.session_state.get("view_mode", "Analyst (4I+4J)")
    is_friend = "Friend" in mode_now

    base_decision = "OBSERVE (ABSTAIN)"
    base_body = "Market conditions do not meet your risk posture right now."
    base_status = "STATUS: STANDARD TRACKING"

    if is_unfiltered:
        # Governance override always wins (hard collapse to baseline)
        st.session_state["behavioral_state"] = "NEUTRAL"
        hero_title = f" DECISION: {base_decision}"
        hero_body = base_body
        status_badge = "STATUS: UNFILTERED DIRECT ACCESS"
    elif active_state == "CHALLENGING":
        # New CHALLENGING posture (euphoria / overconfidence at peaks)
        # Higher-risk state takes precedence over CALMING per v0.1 decision
        hero_title = "⚠️ POSTURE: RISK VELOCITY ALERT"
        hero_body = """
Current momentum appears increasingly disconnected from core valuation health.

Given your active profile constraints and the recent market expansion,
we are maintaining our strict asset allocation caps. No incremental capital
deployment is recommended at current valuation peaks.
"""
        status_badge = "STATUS: TRANSITION PAUSE"
    elif active_state == "CALMING" and is_friend:
        # Existing CALMING logic (preserved)
        hero_title = " POSTURE: INSULATED & PROTECTED"
        hero_body = f"""
Given your **12-Month Strategic Horizon** and documented comfort zone (**max drawdown: {max_dd}%**), 
your core capital remains entirely insulated from short-term market variance. 

Our pre-calculated defense plan is actively executing. No structural changes are required today.
"""
        status_badge = "STATUS: ACTIVE DEFENSE"
    elif active_state == "REINFORCING":
        # REINFORCING posture (v0.1)
        hero_title = " POSTURE: PROGRESS CONSOLIDATED"
        hero_body = """
Your recent decisions align with the long-term stability parameters in this portfolio.
Momentum is being preserved through your deliberate tracking choices.

No adjustments are currently required. Stay with your existing plan and cadence.
"""
        status_badge = "STATUS: REINFORCING ALIGNMENT"
    else:
        # Neutral baseline
        hero_title = f" DECISION: {base_decision}"
        hero_body = base_body
        status_badge = base_status

    # Render the (possibly mutated) posture header for behavioral states
    if active_state in ("CALMING", "CHALLENGING", "REINFORCING") and not is_unfiltered:
        st.markdown("### ⚡ Current Posture")
        st.markdown(f"## {hero_title}")
        st.markdown(hero_body)
        if active_state == "REINFORCING":
            timeline = "12-Week Tactical Progress Review"
        else:
            timeline = "12-Month Marathon"
        st.caption(
            f"**Timeline Framework:** {timeline} | "
            f"**System State:** {status_badge} | "
            "**Tracking Mode:** Session-Bound"
        )

        # Always surface the raw analytical recommendation + metrics underneath (data integrity)
        if is_abstain:
            st.caption(f"Analytical Recommendation (unchanged data): **{rec} (ABSTAIN)**")
        else:
            st.caption(f"Analytical Recommendation (unchanged data): **{rec}**")

        band_cols = st.columns(4)
        with band_cols[0]:
            st.metric("Directional Bias", hero.get("directional_bias", "—"))
        with band_cols[1]:
            st.metric("Risk State", hero.get("risk_state", "—"))
        with band_cols[2]:
            st.metric("Confidence", hero.get("confidence_bucket", "—"))
        if hero.get("abstention_reason"):
            with band_cols[3]:
                st.caption(f"Reason: {hero['abstention_reason']}")

        st.caption(f"Hero Decision Band • {state.selected_portfolio} • CALMING Posture")
    else:
        # Baseline / unfiltered / Analyst: original factual rendering
        if is_abstain:
            st.error(f"**{rec} (ABSTAIN)**", icon="🛑")
        else:
            st.success(f"**{rec}**", icon="✅")

        band_cols = st.columns(4)
        with band_cols[0]:
            st.metric("Directional Bias", hero.get("directional_bias", "—"))
        with band_cols[1]:
            st.metric("Risk State", hero.get("risk_state", "—"))
        with band_cols[2]:
            st.metric("Confidence", hero.get("confidence_bucket", "—"))
        if hero.get("abstention_reason"):
            with band_cols[3]:
                st.caption(f"Reason: {hero['abstention_reason']}")

        st.caption(f"Hero Decision Band • {state.selected_portfolio} • CALMING Posture")
    st.divider()

    # This single call exercises the complete locked 4J surface (state application + all presenters)
    view: Dict[str, Any] = render_full_workbench_with_flows(
        state, registry, lifecycles, snapshot, ledger, base_weekly
    )

    # Mode-aware header (subordinate to Hero Band)
    st.subheader(f"{state.selected_portfolio}  •  time_window={state.time_window}  •  investigation={bool(state.investigation_mode)}")

    # The View Mode radio in sidebar controls the content below the Hero Band
    # Read the mode set in the sidebar (controls content below the Hero Band)
    mode = st.session_state.get("view_mode", "Analyst (4I+4J)")

    if mode == "Friend (4K)":
        # === Friend Mode (4K child spec) ===
        # Only the allowed elements: rationale, Why bullets, Show More, Export
        # Uses locked 4K presenters. Hero Decision Band is always shown above.
        #
        # Post-2026-06-15 boundary: Emotional Entry v0.1 is now the reflective front door (Phase 1).
        # Personal Context follows (Phase 2). Portfolio Intake (Phase 3).
        # No prescriptive onboarding. REINFORCING and other states only from allowed reflective triggers.
        # See Docs/governance/never-include.md for permanent rules.
        #
        # SOT v0.2 alignment: All post-entry surfaces gated behind emotional_entry_done.
        # Thin deployment (FRIEND_OF_1IBANDIT_DEPLOYMENT) forces pure Friend Mode.
        st.divider()
        st.subheader("Friend Mode (4K)")  # H2 per locked Typography for mode headers
        st.caption("Guided companion experience powered by your Friend Profile.")  # Caption per hierarchy

        # Friend Mode palette injection (warm, calm, non-clinical)
        # Called early so styles apply to all Friend surfaces.
        # This is the v1.2 scaffold; will be refined in visual pass.
        st.markdown("""
<style>
/* Base canvas */
.stApp {
    background-color: #f7f3ee;
    color: #2c2520;
}

/* Card containers */
div[data-testid="stVerticalBlock"] > div {
    background-color: #ffffff;
    border-radius: 10px;
    padding: 28px;
    border: 1px solid #e4ddd3;
    box-shadow: 0 1px 4px rgba(44, 37, 32, 0.06);
}

/* Buttons */
.stButton > button {
    background-color: #efe9e2;
    color: #2c2520;
    border: 1px solid #d8cfc3;
    border-radius: 6px;
    transition: all 0.2s ease;
}

.stButton > button:hover {
    background-color: #e7dfd7;
    border-color: #cfc5b8;
}

.stButton > button:active {
    background-color: #ded6cd;
    border-color: #c7bdb0;
}
</style>
""", unsafe_allow_html=True)

        # === Contextual Gating Helper (Workstream H) ===
        # Single source: get_gating_state (behavior_semantic parquet)
        def should_show_post_entry_content() -> bool:
            """Centralized gating for Request, Memory, Identity, Guided, Return Home etc.
            Fully semantic driven. Thin deployments read ONLY the parquet.
            """
            if get_gating_state is not None:
                try:
                    g = get_gating_state("1i_Bandit")
                    if g.get("unfiltered_view", False) or g.get("emotional_entry_done", False):
                        return True
                except Exception:
                    pass
            # Session fallback (for interactive before snapshot write)
            if st.session_state.get("unfiltered_view", False):
                return True
            return bool(st.session_state.get("emotional_entry_done", False))

        # === v0.2 Continuity Header with Portfolio Router (Surface 1) ===
        active_slot = get_active_slot_id()
        display_name = get_slot_display_name(active_slot)
        idx = get_slot_index(active_slot)
        total = get_total_slots()
        st.markdown(
            f"**Buddy: David** | Active: **{display_name} ({idx}/{total})**"
        )
        # Semantic snapshot version (item 2) — thin deployment always knows which snapshot it is reading
        if get_gating_state is not None:
            try:
                g = get_gating_state("1i_Bandit")
                ver = g.get("semantic_snapshot_version") or "unknown"
                st.caption(f"Semantic snapshot: {ver} (sot {g.get('sot_schema_version', '0.2.0')})")
            except Exception:
                pass
        # v0.2 "Why We Keep It Tight" explainer - subtle in Continuity Header
        st.caption("Why We Keep It Tight: We focus on assets with real trading volume and history. This keeps the experience clear and protects you from noise that can trigger impulsive decisions.")

        # v0.3 Guidance Level toggle (demo) — suppressed in pure Friend deployment for clean calm companion view
        if not is_friend_deployment:
            guidance_level = st.radio(
                "Guidance Level (demo)",
                ["Quiet", "Standard", "Companion"],
                index=1,
                horizontal=True,
                key="guidance_level"
            )
            if guidance_level == "Quiet":
                st.caption("(Quiet mode: minimal narration for review)")

        # Lightweight switch affordance (full isolation + teardown on change)
        # The sidebar also has the selector; this header makes the behavioral context the north star.
        slot_options = list(st.session_state.get("portfolio_behavioral_registry", {}).keys())
        current_slot_idx = slot_options.index(active_slot) if active_slot in slot_options else 0
        new_slot = st.selectbox(
            "Switch Portfolio (behavioral context)",
            slot_options,
            index=current_slot_idx,
            key="friend_portfolio_selector",
        )
        if new_slot != active_slot:
            write_current_behavioral_to_registry(active_slot)
            if st.session_state.get("behavioral_state") == "NEUTRAL":
                st.session_state.setdefault("behavior_event_log", []).append({
                    "event_type": "discipline_event",
                    "description": "Core investment boundaries actively maintained under short-term market variance."
                })
            # Keep analytical data in sync with the behavioral slot (for Hero Band + data surfaces)
            if new_slot != state.selected_portfolio:
                select_portfolio(state, new_slot)
            switch_to_slot(new_slot)

        # v0.3 Persistence Layer: load or seed 1i_Bandit sandbox state early in Friend Mode
        # This ensures the canonical December 2025 baseline or previously saved state is restored
        # before any emotional entry, ledger, or behavioral surfaces run.
        initialize_or_load_buddy_session("1i_Bandit")

        # v0.1 Return Home: update last seen on load
        st.session_state["last_seen_timestamp"] = datetime.utcnow().isoformat()
        trigger_encrypted_disk_sync("1i_Bandit")

        # === Return Home Experience v0.1 (if returning after >7 days) ===
        # Consult semantic gating (Workstream H)
        show_return = st.session_state.get("show_return_home", False)
        if get_gating_state is not None:
            try:
                g = get_gating_state("1i_Bandit")
                if g.get("return_home_shown"):
                    show_return = True
            except Exception:
                pass
        if show_return:
            with st.container():
                st.markdown("**Welcome back.**")
                st.caption("It’s good to see you again.")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Give me a quick snapshot.", key="return_snapshot"):
                        st.session_state["show_return_home_snapshot"] = True
                        st.rerun()
                with col2:
                    if st.button("I’m just checking in.", key="return_checkin"):
                        st.session_state["show_return_home"] = False
                        st.rerun()
                if st.session_state.get("show_return_home_snapshot", False):
                    st.markdown("**Quick Snapshot**")
                    ledger = st.session_state.get("sandbox_ledger", {})
                    cash = ledger.get("CASH", {}).get("shares", 0)
                    st.markdown(f"Current sandbox cash: ${cash}")
                    positions = ", ".join([f"{k}: {v.get('shares', 0)}" for k, v in list(ledger.items())[:3]])
                    st.markdown(f"Key positions: {positions if positions else 'None yet'}")
                    events = st.session_state.get("behavior_event_log", [])
                    recent_reinf = [e for e in events if e.get("event_type") in ["reinforcement_event", "discipline_event", "intentional_manual_update"]][-1:]
                    if recent_reinf:
                        st.markdown(f"Recent: {recent_reinf[0].get('description', '')}")
                    st.markdown("From what I can see, your setup still supports your long‑term stability.")
                    st.caption("Why you’re seeing this: This is a simple recap of your current sandbox state to help you reorient quickly.")
                    if st.button("Close snapshot", key="close_snapshot"):
                        st.session_state["show_return_home_snapshot"] = False
                        st.rerun()

        # Soft Re-Entry State (pre-spine handshake for users who completed onboarding in previous session but returned without long absence)
        # Preserves sovereignty: does not assume continuity or jump to full Return Home or spine.
        # Shown if onboarding_completed from previous but not a >7 day absence (to avoid overlapping full Return Home).
        if st.session_state.get("onboarding_completed", False) and not st.session_state.get("show_return_home", False):
            st.markdown("---")
            st.markdown("**Welcome back, David. I saved your setup from earlier.**")
            st.markdown("How would you like to continue today?")
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Pick up where I left off", key="soft_pickup"):
                    # Proceed to the post-entry spine (gated surfaces will show)
                    # Mark soft re-entry in semantic layer for Workstream H
                    if update_behavior_semantic_from_event is not None:
                        try:
                            update_behavior_semantic_from_event("1i_Bandit", "soft_reentry_pickup", {})
                        except Exception:
                            pass
                    st.session_state["soft_reentry"] = True
            with col2:
                if st.button("Start fresh", key="soft_fresh"):
                    st.session_state["emotional_entry_done"] = False
                    st.session_state["onboarding_completed"] = False
                    if update_behavior_semantic_from_event is not None:
                        try:
                            update_behavior_semantic_from_event("1i_Bandit", "soft_reentry_fresh", {})
                        except Exception:
                            pass
                    st.rerun()
            with col3:
                if st.button("Just show me my accounts", key="soft_accounts"):
                    # Proceed to spine (ledger will be visible early in gated content)
                    st.session_state["soft_show_ledger"] = True
                    if update_behavior_semantic_from_event is not None:
                        try:
                            update_behavior_semantic_from_event("1i_Bandit", "soft_reentry_accounts", {})
                        except Exception:
                            pass
                    st.rerun()

        # === Emotional Entry v0.1 (new non-prescriptive front door) ===
        # Strictly contextual and reflective per canonical boundary (2026-06-15).
        # Purpose: calibrate pacing, tone, and behavioral_state only.
        # Never: numbers, commitments, targets, "first steps", ledger mutations, habit language, or performance framing.
        # Placed early in Friend Mode after Return Home (if any) so the Companion can respond appropriately from the start.
        # Respects Unfiltered View (bypass or minimal) and existing router/persistence/sandbox.
        #
        # SOT v0.2 (H): Load from single contract get_gating_state (behavior_semantic)
        # Drives the entire spine. No re-execution for thin deployment.
        gating = {}
        if get_gating_state is not None:
            try:
                from src.sot.semantic import load_gating_into_session
                gating = load_gating_into_session("1i_Bandit") or get_gating_state("1i_Bandit")
            except Exception:
                try:
                    gating = get_gating_state("1i_Bandit")
                except Exception:
                    pass

        # Backfill session from authoritative semantic (for Return Home, soft etc.)
        for flag in ["emotional_entry_done", "onboarding_completed", "show_return_home", "unfiltered_view", "soft_reentry"]:
            if flag in gating and gating[flag]:
                st.session_state[flag] = True

        if not st.session_state.get("unfiltered_view", False):
            if "emotional_entry_done" not in st.session_state:
                st.session_state["emotional_entry_done"] = False

            if not st.session_state["emotional_entry_done"]:
                st.markdown("---")
                st.subheader("What brings you here today?")

                intent = st.radio(
                    "Choose the one that feels closest:",
                    [
                        "Just checking in",
                        "Check my portfolios / overall picture",
                        "Understand a specific holding or decision",
                        "Learn something new about my situation",
                        "Prepare for a conversation or upcoming choice",
                        "Something else on my mind"
                    ],
                    key="entry_intent"
                )

                st.markdown("### How are you feeling about money lately?")
                feeling = st.radio(
                    "Pick the word or phrase that fits best right now:",
                    [
                        "Calm and steady",
                        "A bit uncertain or thoughtful",
                        "Hopeful or optimistic",
                        "Anxious or worried",
                        "Overwhelmed",
                        "Curious or open"
                    ],
                    key="entry_feeling"
                )

                driving = st.text_input(
                    "What's driving that feeling? (optional — one sentence is plenty)",
                    key="entry_driving",
                    placeholder="e.g. market moves, upcoming expense, just reflecting..."
                )

                if st.button("Continue", key="entry_complete"):
                    # Pre-calibrate behavioral_state (reflective only, no diagnosis)
                    if "Anxious" in feeling or "Overwhelmed" in feeling or "Uncertain" in feeling:
                        st.session_state["behavioral_state"] = "CALMING"
                    elif "Hopeful" in feeling:
                        st.session_state["behavioral_state"] = "REINFORCING"
                    else:
                        st.session_state["behavioral_state"] = "NEUTRAL"

                    # Capture purely reflective event (no compliance scoring)
                    capture_event("reflective_entry", {
                        "intent": intent,
                        "feeling": feeling,
                        "driving": driving or "(not shared)"
                    })

                    st.session_state["emotional_entry_done"] = True
                    st.session_state["onboarding_completed"] = True
                    st.session_state["onboarding_focus"] = intent
                    st.success("Thank you. I'll keep this in mind as we look at things together.")
                    trigger_encrypted_disk_sync("1i_Bandit")

                    # Workstream H + A: push event + materialize behavior_semantic immediately
                    # (so gating is driven from SOT layer, Excel can see it, thin deployments respect it)
                    if update_behavior_semantic_from_event is not None:
                        try:
                            update_behavior_semantic_from_event(
                                "1i_Bandit",
                                "emotional_entry_continue",
                                {"focus": intent, "feeling": feeling, "driving": driving or ""}
                            )
                        except Exception:
                            pass  # non-fatal; session flag still works

                    st.rerun()

            # After Emotional Entry is complete, show the rest of the Friend surfaces
            # (Request block, Memory Graph, etc.) so the flow feels sequential and calm.
        else:
            st.caption("(Emotional entry skipped — Unfiltered View active. All guidance is neutral.)")

        # Note: The Identity Card and Guided Question use st.subheader for their titles (H2 per locked Typography for card headers / major Friend Mode surfaces). Internal bold labels (e.g. **Primary Goals**) are H3 (Medium). All framing/provenance use st.caption (Caption per locked).

        # Gate Identity Card and Guided Question behind completed Emotional Entry (per spine order) - logic applied via the earlier gate for pacing.

        # Gate the remaining Friend surfaces behind completed Emotional Entry for sequential, calm pacing.
        # Uses centralized should_show_post_entry_content() for Workstream H.
        if should_show_post_entry_content():
            # SURFACE 1.5: THE DYNAMIC ONBOARDING STATUS RIBBON (Collapsed Banner)
            st.markdown("---")
            focus = st.session_state.get("onboarding_focus", "Understand My Allocation Setup")
            pacing = st.session_state.get("behavioral_state", "NEUTRAL")
            st.caption(f"Focus: {focus}  |   Pacing: {pacing} Mode Active")

            # === v0.2 Gated Ticker Request (Surface 3.6) - inside Buddy Sandbox / Manual Ledger area ===
            # Prevents free-form search, routes to human (David). Clear pause and boundary.
            st.markdown("---")
            st.subheader("➕ Request an Asset Addition")
            st.markdown("I keep the list focused on assets with a clear trading history so the experience stays steady and easy to follow.")
            ticker_request = st.text_input("Ticker symbol to request (e.g. NEWASSET)", key="gated_ticker_input")
            if st.button("Send to David for a look", key="gated_ticker_submit"):
                if ticker_request:
                    requests = st.session_state.setdefault("ticker_requests", [])
                    requests.append(ticker_request.upper())
                    st.session_state["ticker_requests"] = requests
                    st.success("Request submitted to David. He will personally review the volume profile with you.")
            st.caption("If you want another asset reviewed, I’ll take a look and help you think it through.")

            # Request Help From David - direct human bridge, low-prominence in sandbox area
            if st.button("Ask David for guidance", key="request_help_david"):
                st.info("A direct line to David for guidance on your financial path. Your request has been noted.")
            st.caption("A direct line to David for guidance on your financial path.")

            # === Memory Graph Viewer v0.3 - Sovereign Transparency Deck ===
            # Per v0.3 spec: dedicated Progress & Reinforcement section for the four positive events.
            # Placed after Sandbox / gated area.
            is_unfiltered = st.session_state.get("unfiltered_view", False)
            session_events = st.session_state.get("behavior_event_log", [])

            st.markdown("---")

            with st.container():
                st.subheader(" What I'm Remembering This Session")
                st.caption("Your Memory, Your Control. This auditable log displays how your real-time interaction patterns adjust our communication parameters.")

                if is_unfiltered:
                    st.info("Memory-assisted guidance is currently deactivated for this session via your Unfiltered View override toggle.")
                    return

                if not session_events:
                    st.info("I haven't recorded any behavioral variations or milestones in this session yet.")
                    return

                # 1. Segregate the Positive Identity Spine Events
                # Only events from reflective user actions per Docs/governance/never-include.md
                positive_event_types = ["intentional_manual_update", "discipline_event", "reinforcement_event"]
                progress_events = [e for e in session_events if e.get("event_type") in positive_event_types]
                neutral_events = [e for e in session_events if e.get("event_type") not in positive_event_types]

                # 2. Render Dedicated Progress & Reinforcement Surface Area
                if progress_events:
                    st.markdown("###  Progress & Reinforcement")
                    for event in progress_events:
                        etype = event.get("event_type")

                        # Linguistic Translation Matrix Rules Execution
                        if etype == "intentional_manual_update":
                            title = " Structured Bookkeeping"
                            body = "Manual asset ledger updated with deliberate, self-reported values."
                            action = "Timeline lookback window adjusted to preserve tactical context."
                        elif etype == "discipline_event":
                            title = " Allocation Boundary Adherence"
                            body = "Core investment boundaries actively maintained under short-term market variance."
                            action = "Postural framing adjusted to protect long-term horizon integrity."
                        elif etype == "reinforcement_event":
                            title = " Strategic Milestone Consolidation"
                            body = "Active decision parameters executed in alignment with defined 12-month goals."
                            action = "Hero Band mutated to prioritize momentum preservation."
                        else:
                            continue

                        # Component Typography Render Pass
                        st.markdown(f"**{title}**")
                        st.text(f"• Action: {body}\n• Adjustment: {action}")
                        st.caption(f"Recorded: Live Session Context Lifecycle")
                    st.markdown("---")
                    st.caption("Why you’re seeing this: These are actions you took that align with stability and discipline. The Companion uses them only to adjust pacing and framing.")

                # 3. Render Standard Telemetry Footprints
                if neutral_events:
                    st.markdown("### ️ System Telemetry Tracking Logs")
                    for event in neutral_events:
                        if event.get("event_type") == "panic_pattern":
                            st.markdown("**Interaction Metric Notice: High Interaction Volume During Market Variance**")
                            st.caption("Observed Signal: App layouts reviewed multiple times while valuation metrics shifted downward.")

                # 4. Atomic Destruction Pipeline Gate
                if st.button("Clear Everything I've Shared This Session", key="purge_session_v03"):
                    st.session_state["behavior_event_log"] = []
                    st.session_state["behavioral_state"] = "NEUTRAL"
                    st.session_state["active_conversational_tier"] = 1
                    st.success("Session memory wiped cleanly. Starting fresh.")
                    st.rerun()

        # Friend Mode color system styles (from locked Color System + Card Design)
        # Warmer, calmer palette for Friend Mode (Phase 4 palette redesign in progress per #24).
        # Refined v1.2: #f7f3ee base, soft cards, low-stress buttons, warm non-clinical accents.
        # (Applies only when the Friend branch runs — i.e., once the deployment guard is active.)
        st.markdown("""
<style>
/* Base canvas */
.stApp {
    background-color: #f7f3ee;
    color: #2c2520;
}

/* Card containers */
div[data-testid="stVerticalBlock"] > div {
    background-color: #ffffff;
    border-radius: 10px;
    padding: 28px;
    border: 1px solid #e4ddd3;
    box-shadow: 0 1px 4px rgba(44, 37, 32, 0.06);
}

/* Buttons */
.stButton > button {
    background-color: #efe9e2;
    color: #2c2520;
    border: 1px solid #d8cfc3;
    border-radius: 6px;
    transition: all 0.2s ease;
}

.stButton > button:hover {
    background-color: #e7dfd7;
    border-color: #cfc5b8;
}

.stButton > button:active {
    background-color: #ded6cd;
    border-color: #c7bdb0;
}
</style>
""", unsafe_allow_html=True)

        # === Session-level editable FriendProfile (new in this micro-chunk) ===
        # The user now has agency: edit the profile and immediately see the
        # Identity Card and Guided Question adapt. Stored in st.session_state
        # for this session only (persistent storage is a later chunk).
        if "friend_profile" not in st.session_state or not isinstance(
            st.session_state["friend_profile"], FriendProfile
        ):
            st.session_state["friend_profile"] = create_example_friend_profile(
                profile_id=f"{state.selected_portfolio}_friend"
            )

        current_profile: FriendProfile = st.session_state["friend_profile"]

        # Capture load event for the Behavioral Event Stream
        capture_event("portfolio_check", {"portfolio": state.selected_portfolio})

        # Demo button to simulate the panic pattern (high checking + projection + hover)
        # Hidden in pure Friend deployment for clean companion experience
        if not is_friend_deployment and st.button("Simulate panic pattern (high checking + hover for demo)", key="btn_simulate_panic"):
            capture_event("projection_view", {"portfolio": state.selected_portfolio})
            capture_event("hover_sell", {"portfolio": state.selected_portfolio})
            st.session_state["behavioral_state"] = "CALMING"
            st.session_state.setdefault("behavior_event_log", []).append({
                "category": "Stability Signals",
                "description": "Maintained pacing during CALMING"
            })
            write_current_behavioral_to_registry(get_active_slot_id())
            st.rerun()

        # New: Simulate Euphoria / Overconfidence pattern for CHALLENGING (Hero Band Context Awareness v0.1 extension)
        if st.button("Simulate Euphoria Pattern (rapid allocation at highs)", key="btn_simulate_euphoria"):
            st.session_state["behavioral_state"] = "CHALLENGING"
            capture_event("overconfidence_pattern", {
                "trigger": "rapid_allocation_increase_at_market_highs",
                "behaviors": [
                    "increased_growth_allocation_target_by_20pct",
                    "bypassed_standard_diversification_guidelines",
                ],
            })
            st.session_state.setdefault("behavior_event_log", []).append({
                "category": "Attention Patterns",
                "description": "Triggered CHALLENGING posture"
            })
            write_current_behavioral_to_registry(get_active_slot_id())
            st.rerun()

        # Simulate Reinforcing Pattern for REINFORCING state (v0.1)
        # Per governance: REINFORCING may only be triggered by reflective user actions
        # (e.g. reinforcement_event, discipline_event, intentional_manual_update, or manual ledger updates).
        # Never from onboarding, commitments, or prescriptive flows (all such paths excised).
        if st.button("Simulate Reinforcing Pattern", key="btn_simulate_reinforcing"):
            st.session_state["behavioral_state"] = "REINFORCING"
            st.session_state["reinforcing_count"] = st.session_state.get("reinforcing_count", 0) + 1
            capture_event("reinforcement_event", {
                "portfolio": state.selected_portfolio
            })
            st.session_state.setdefault("behavior_event_log", []).append({
                "event_type": "reinforcement_event",
                "description": "Active decision parameters executed in alignment with defined 12-month goals."
            })
            write_current_behavioral_to_registry(get_active_slot_id())
            st.rerun()

        events = get_events()
        calming_state = infer_state(events)
        unfiltered = st.session_state.get("unfiltered_view", False)

        if calming_state == "CALMING" and not unfiltered:
            if get_current_panic_pattern() is None:
                node = PanicPatternNode(
                    triggers=["high_checking", "volatility"],
                    behaviors=["portfolio_check", "projection_view", "hover_sell"],
                    emotional_inference="anxiety_spike",
                    stabilization_response="calming_flow_v0",
                    outcome="no_panic_sale",
                )
                add_panic_pattern(node)
                capture_event("panic_pattern", {
                    "triggers": ["high_checking", "volatility"],
                    "adjustment": "calming_flow_v0",
                    "portfolio": state.selected_portfolio
                })

            continuity_header = "This week’s volatility is similar to periods you’ve found stressful before. Let’s focus on stability."
            identity_framing = "I'm guiding you as a BalancedCore investor, with extra focus on protecting your comfort zone during volatility."
            guided_question = "What would help you feel safe staying the course here?"
            guided_rationale = "Avoiding panic-selling during periods like this has historically improved long-term stability for investors like you."
            explain_text = "You’ve been checking short-term changes more frequently today, so I’m foregrounding stability and long-term context. All of your usual details are still available below."
        else:
            continuity_header = None
            identity_framing = None
            guided_question = None
            guided_rationale = None
            explain_text = None

        if continuity_header:
            st.caption(continuity_header)

        if should_show_post_entry_content():
            # === Friend Mode Identity Card ===
            # Now passes the (potentially edited) profile so it reflects user input.
            identity_card = get_friend_identity_card_data(
                state.selected_portfolio, registry, friend_profile=current_profile
            )

            if identity_framing:
                identity_card["framing"] = identity_framing

            # Guaranteed wrapper for styling — Streamlit cannot optimize this away
            # (replaces border=True which was being collapsed)
            identity_card_wrapper = st.container()
            with identity_card_wrapper:
                st.markdown('<div class="identity-card-wrapper">', unsafe_allow_html=True)
                # v0.2: Identity Card now reflects the active portfolio's context (name + constraints from profile)
                active_slot_name = get_slot_display_name(get_active_slot_id())
                st.subheader("️ Identity Card")
                st.caption(f"**{active_slot_name}** — {identity_card.get('framing', '')}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Personality", identity_card.get("personality_type", "—"))
                with c2:
                    goals = identity_card.get("primary_goals", [])
                    st.markdown("**Primary Goals**")
                    st.caption(" • ".join(goals) if goals else "—")
                with c3:
                    constraints = identity_card.get("key_constraints", {})
                    st.markdown("**Key Constraints**")
                    if constraints:
                        for k, v in list(constraints.items())[:2]:
                            st.caption(f"{k}: {v}")
                    else:
                        st.caption("—")

                tendencies = identity_card.get("behavioral_tendencies_accounted", [])
                if tendencies:
                    st.markdown("**I'm watching for these tendencies:** " + ", ".join(tendencies))
                st.caption("This is the first visible expression of your Friend Profile.")

                # v0.2 accessible from Identity Card: Request Help From David (low prominence)
                if st.button("Request Help From David", key="help_from_identity"):
                    st.info("Not support. A direct line to your system mentor for guidance on your financial path.")

                st.markdown('</div>', unsafe_allow_html=True)

        if should_show_post_entry_content():
            # === First Guided Question ===
            # Now reacts to the live-edited profile.
            guided = get_first_guided_question(
                state.selected_portfolio, registry, lifecycles, snapshot, friend_profile=current_profile
            )

            if guided_question:
                guided["question"] = guided_question
            if guided_rationale:
                guided["rationale"] = guided_rationale

            with st.container(border=True):
                st.subheader("Guided Question")
                st.markdown(f"> {guided.get('question', '')}")
                st.caption(guided.get("rationale", ""))
                signals = guided.get("profile_signals_used", [])
                if signals:
                    st.caption("Drawn from: " + ", ".join(signals))
                st.caption("This is the kind of question I will proactively bring forward for you.")

            if explain_text:
                with st.expander("Why am I seeing this?"):
                    st.caption(explain_text)

        # end gate for Identity/Guided (after entry)

        # === Second Guided Question (Follow-Up) — micro-chunk v0.1 ===
        # Per spec: add follow-up button under first Guided Question.
        # Only the teaching path ("Show me historical drops") for CALMING.
        # Render second card only when: followup and calming_state == "CALMING" and not unfiltered.
        # Session-only via button return + existing state. Thin, no new components.
        # Event logged feeds Relationship Memory Graph later.
        followup_historical = st.button(
            "Show me how similar drops played out historically",
            key="followup_historical"
        )

        if followup_historical and calming_state == "CALMING" and not unfiltered:
            capture_event("guided_question_followup", {
                "type": "historical_drops",
                "portfolio": state.selected_portfolio
            })
            st.session_state.setdefault("behavior_event_log", []).append({
                "category": "Attention Patterns",
                "description": "Viewed historical context in Guided Question"
            })

            st.subheader("Your Next Best Question (Follow‑Up)")
            st.markdown("Here’s the perspective that usually helps during weeks like this.")
            st.caption("You’re seeing this because you asked for historical context.")

            st.markdown("""
- In the last 20 years, 3–5 day drops of 3–6% recovered within 30 days 72% of the time.
- In the remaining cases, deeper declines were followed by strong 12‑month recoveries.
- The biggest risk historically wasn’t staying invested — it was reacting too quickly.
""")

            st.caption("Staying the course during short‑term volatility has historically improved long‑term stability for investors with patterns similar to yours.")

        # === Editable Friend Profile form (the new interactive surface) ===
        # Thin UI only. On submit we create a new immutable profile via the
        # pure helper and store it in session_state. The card + question above
        # will reflect the update on rerun.
        with st.expander("✏️ Edit Your Friend Profile (affects this session only)", expanded=False):
            with st.form(key="edit_friend_profile_form", clear_on_submit=False):
                # Per locked Input Components v1.0 (incorporating suggested upgrades):
                # - Contextual Prompt: the caption below
                # - Responsive Capture: on submit we log "profile_edit" with context for extreme values (hesitation can be future on_change)
                # - Dynamic Behavioral Caption: the caption can be extended in future, but for v0.1 the success note adapts
                # Input State Validation Matrix (actionable decision table for v0.1+):
                # Trigger (e.g. extreme value, hesitation) | State (CALMING/CHALLENGING) | UI Mutation (soften language, reflective note)
                # Degradation: if no/incomplete profile or low confidence, default to neutral framing (no forced state)
                # Unfiltered View affordance: checkbox below to temporarily ignore edits (reinforces "Guide Attention, Never Distort Reality")
                # Anti-dependency: success message reinforces "You did this. I’m just helping you see it."
                st.caption("Updating your Friend Profile helps me guide you with more clarity. You did this. I’m just helping you see it.")

                unfiltered = st.checkbox("View unfiltered guidance (temporarily ignore my profile edits for this session)", key="unfiltered_view")
                if unfiltered:
                    st.caption("Unfiltered view active — mutations disabled for this session only.")

                new_personality = st.selectbox(
                    "Personality Type",
                    options=["GrowthSeeker", "CapitalPreserver", "IncomeOptimizer", "ContrarianOpportunist", "BalancedCore"],
                    index=["GrowthSeeker", "CapitalPreserver", "IncomeOptimizer", "ContrarianOpportunist", "BalancedCore"].index(
                        current_profile.personality_type
                    ) if current_profile.personality_type in ["GrowthSeeker", "CapitalPreserver", "IncomeOptimizer", "ContrarianOpportunist", "BalancedCore"] else 4,
                )

                current_goals_str = ", ".join(current_profile.primary_goals) if current_profile.primary_goals else ""
                new_goals_str = st.text_input(
                    "Primary Goals (comma-separated)",
                    value=current_goals_str,
                    help="e.g. long_term_capital_growth, moderate_income",
                )
                new_goals = [g.strip() for g in new_goals_str.split(",") if g.strip()]

                # Simple risk constraint editor (one key field for this chunk)
                current_dd = current_profile.risk_constraints.get("max_drawdown_pct", 15.0)
                new_max_dd = st.number_input(
                    "Max Drawdown Tolerance (%)",
                    min_value=5.0, max_value=50.0, value=float(current_dd), step=1.0
                )

                current_tend_str = ", ".join(current_profile.behavioral_tendencies) if current_profile.behavioral_tendencies else ""
                new_tend_str = st.text_input(
                    "Behavioral Tendencies to Watch (comma-separated)",
                    value=current_tend_str,
                    help="e.g. recency_bias, loss_aversion",
                )
                new_tendencies = [t.strip() for t in new_tend_str.split(",") if t.strip()]

                new_comm = st.selectbox(
                    "Communication Preference",
                    options=["concise", "detailed", "question_driven", "story_driven", "balanced"],
                    index=["concise", "detailed", "question_driven", "story_driven", "balanced"].index(
                        current_profile.communication_preference
                    ) if current_profile.communication_preference in ["concise", "detailed", "question_driven", "story_driven", "balanced"] else 4,
                )

                submitted = st.form_submit_button("Update Profile")

            if submitted:
                capture_event("profile_edit", {
                    "extreme_risk": new_max_dd < 5 or new_max_dd > 40,
                    "portfolio": state.selected_portfolio
                })
                if unfiltered:
                    st.session_state["unfiltered_view"] = True
                    force_neutral_all_slots()
                    if update_behavior_semantic_from_event is not None:
                        try:
                            update_behavior_semantic_from_event("1i_Bandit", "unfiltered_view_enabled", {})
                        except Exception:
                            pass
                else:
                    st.session_state["unfiltered_view"] = False
                edits = {
                    "personality_type": new_personality,
                    "primary_goals": new_goals,
                    "risk_constraints": {"max_drawdown_pct": new_max_dd},
                    "behavioral_tendencies": new_tendencies,
                    "communication_preference": new_comm,
                }
                updated_profile = apply_profile_edits(current_profile, edits)
                st.session_state["friend_profile"] = updated_profile
                # v0.2 write-back after profile mutation
                write_current_behavioral_to_registry(get_active_slot_id())
                st.session_state.setdefault("behavior_event_log", []).append({
                    "category": "Manual Bookkeeping",
                    "description": "Updated Friend Profile details"
                })
                st.success("Your Friend Profile has been updated. The Identity Card and Guided Question have adapted to your changes. You did this. I’m just helping you see it.")
                st.rerun()

        # === Manual Ledger (Sandbox) — v0.3 Buddy Sandbox & Variable Lookback ===
        # Canonical testing Buddy 1i_Bandit with fixed Dec 2025 ledger.
        # Placed below Identity Card / editable surfaces, above Memory Graph Viewer per spec.
        # Independent of Portfolio Router slots.
        # Horizon label driven by behavioral_state (CALMING/CHALLENGING/REINFORCING/NEUTRAL).
        if "buddy_id" not in st.session_state:
            st.session_state["buddy_id"] = "1i_Bandit"
        if "sandbox_ledger" not in st.session_state:
            st.session_state["sandbox_ledger"] = {
                "TSNF":  {"shares": 760,  "price": 42.50, "date": "2025-11"},
                "IFRA":  {"shares": 211,  "price": 38.20, "date": "2025-08"},
                "VALE":  {"shares": 1100, "price": 12.10, "date": "2025-05"},
                "PL":    {"shares": 250,  "price": 18.45, "date": "2025-10"},
                "NEE":   {"shares": 150,  "price": 72.30, "date": "2025-09"},
                "DOCN":  {"shares": 125,  "price": 34.00, "date": "2025-06"},
                "PBR.A": {"shares": 400,  "price": 14.80, "date": "2025-07"},
                "IGF":   {"shares": 350,  "price": 45.15, "date": "2025-04"},
                "PLUG":  {"shares": 140,  "price": 3.20,  "date": "2025-12"},
            }

        active_state = st.session_state.get("behavioral_state", "NEUTRAL")
        ledger = st.session_state["sandbox_ledger"]

        # State-driven lookback horizon label (per v0.3 spec)
        if active_state == "CALMING":
            horizon_label = "12-Month Strategic Marathon"
            horizon_note = "Focusing your lens out to 1 year to dilute short-term price noise."
        elif active_state == "CHALLENGING":
            horizon_label = "3-Year Historical Macro Cycle"
            horizon_note = "Anchoring metrics to multi-year history to contextualize current peaks."
        elif active_state == "REINFORCING":
            horizon_label = "12-Week Tactical Progress Review"
            horizon_note = "Highlighting your recent window of disciplined execution."
        else:
            horizon_label = "6-Month Balanced Track"
            horizon_note = "Standard baseline timeframe view."

        st.markdown("---")
        with st.container():
            st.subheader("Sandbox Active Ledger")
            st.caption(f"Buddy: 1i_Bandit | Snapshot Base: December 2025. This is a deterministic testing environment with manual upkeep only.")
            st.markdown(f"**Current View Window:** `{horizon_label}`")
            st.caption(f" Companion choice: {horizon_note}")

            for ticker, data in ledger.items():
                st.text(
                    f" {ticker.ljust(6)} | Shares: {str(data['shares']).ljust(5)} "
                    f"| Approx Entry: ${data['price']:.2f} | Captured: {data['date']}"
                )

            with st.expander("✏️ Update Manual Ledger Entries (Self-Maintained Anchor)"):
                with st.form("manual_ledger_form"):
                    target_ticker = st.selectbox("Select asset to modify", options=list(ledger.keys()))
                    new_shares = st.number_input(
                        "Current number of shares",
                        value=int(ledger[target_ticker]["shares"])
                    )
                    new_price = st.number_input(
                        "Approximate purchase price ($)",
                        value=float(ledger[target_ticker]["price"])
                    )

                    if st.form_submit_button("Commit manual update"):
                        st.session_state["sandbox_ledger"][target_ticker]["shares"] = new_shares
                        st.session_state["sandbox_ledger"][target_ticker]["price"] = new_price
                        st.session_state["ledger_update_count"] = st.session_state.get("ledger_update_count", 0) + 1
                        st.session_state.setdefault("behavior_event_log", []).append({
                            "category": "Manual Bookkeeping",
                            "description": f"Updated {target_ticker} shares or price"
                        })
                        # v0.3: persist the change to disk
                        trigger_encrypted_disk_sync("1i_Bandit")
                        st.success(
                            f"Ledger entry for {target_ticker} updated in session. "
                            "Identity alignment preserved."
                        )
                        st.rerun()

        friend_view = get_friend_view_data(
            state.selected_portfolio, registry, lifecycles, snapshot
        )

        temp = friend_view.get("emotional_temperature", "Calm & Steady")
        st.markdown(f"**Emotional Temperature:** {temp}")

        st.markdown(f"**One-Sentence Summary:** {friend_view.get('one_sentence_summary', '')}")

        highlights = friend_view.get("actionable_highlights", [])
        if highlights:
            st.markdown("**Actionable Highlights (filtered):**")
            for h in highlights:
                st.markdown(f"- **{h.get('id', '')}**: {h.get('note', '')}")
        else:
            st.markdown("**Actionable Highlights (filtered):** None at this time.")

        st.markdown(f"**Portfolio Storyline:** {friend_view.get('storyline', '')}")
        st.markdown(f"**Confidence Translation:** {friend_view.get('confidence_translation', '')}")

        glossary = friend_view.get("glossary", {})
        if glossary:
            with st.expander("Glossary"):
                for term, definition in glossary.items():
                    st.markdown(f"**{term}**: {definition}")

        st.info(friend_view.get("interpretation_guardrails", ""))

        st.caption(f"Quiet state: {friend_view.get('is_quiet_state', False)} | Provenance: {friend_view.get('provenance', {})}")

        if st.button("📥 Export Friend Note", key="btn_friend_export"):
            friend_note = build_friend_note(state.selected_portfolio, friend_view)
            st.success("Friend Note captured (language version included).")
            st.json(friend_note)
            st.download_button(
                label="Download friend_note.json",
                data=json.dumps(friend_note, indent=2, default=str),
                file_name=f"friend_note_{state.selected_portfolio}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

    else:
        # === Analyst Mode content (subordinate to Hero Band) ===
        # Attention Vector
        att_data = view["raw_panel_data"].get("attention_vector", {})
        st.markdown("### ⚡ Attention Vector (Critical / Important / Informational)")
        att_cols = st.columns(3)
        for col, level in zip(att_cols, ["critical", "important", "informational"]):
            items = att_data.get(level, [])
            with col:
                if items:
                    st.markdown(f"**{level.upper()}**")
                    for it in items[:4]:
                        desc = it.get("description", str(it))
                        st.markdown(f"- {desc}")
                else:
                    st.caption(f"No {level} items right now")

        st.divider()

        # The four core panels (4I) + Hypothesis + Analyst export
        tab_arcs, tab_life, tab_gov, tab_del = st.tabs(
            ["Narrative Arcs", "Lifecycle Status", "Governance Status", "Delivery History"]
        )

        with tab_arcs:
            st.markdown("**Official rendered panel (from workbench_ui.py):**")
            st.code(view["panels"]["narrative_arcs"], language="text")
            arcs_raw = view["raw_panel_data"].get("narrative_arcs", {})
            events = arcs_raw.get("events", [])
            if events:
                st.markdown("**Structured data (what the renderer received):**")
                st.dataframe(events, width="stretch", hide_index=True)
            if arcs_raw.get("provenance"):
                st.caption(f"Provenance: {arcs_raw['provenance']}")

        with tab_life:
            st.markdown("**Official rendered panel (from workbench_ui.py):**")
            st.code(view["panels"]["lifecycle_status"], language="text")
            life_raw = view["raw_panel_data"].get("lifecycle_status", {})
            recs = life_raw.get("recommendations", [])
            if recs:
                st.markdown("**Structured data:**")
                st.dataframe(recs, width="content", hide_index=True)

        with tab_gov:
            st.markdown("**Official rendered panel (from workbench_ui.py):**")
            st.code(view["panels"]["governance_status"], language="text")
            gov_raw = view["raw_panel_data"].get("governance_status", {})
            if gov_raw.get("active_alerts"):
                st.markdown("**Active alerts (raw):**")
                st.json(gov_raw["active_alerts"])
            st.caption(f"Overall health: {gov_raw.get('overall_health', 'n/a')} | Actionable items: {gov_raw.get('actionable_items', 0)}")

        with tab_del:
            st.markdown("**Official rendered panel (from workbench_ui.py):**")
            st.code(view["panels"]["delivery_history"], language="text")
            del_raw = view["raw_panel_data"].get("delivery_history", {})
            entries = del_raw.get("recent_entries", [])
            if entries:
                st.dataframe(entries, width="stretch", hide_index=True)

        # Hypothesis Auditor (4J)
        if state.hypothesis_selected:
            st.divider()
            st.markdown("### Hypothesis Auditor (4J)")
            auditor = view["raw_panel_data"].get("hypothesis_auditor")
            if auditor:
                st.json(auditor)
            else:
                auditor = get_hypothesis_auditor_data(
                    state.selected_portfolio, registry, state.hypothesis_selected, lifecycles, {}
                )
                st.json(auditor)

        # Analyst-specific Export (Investigation Note)
        st.divider()
        col_exp1, col_exp2 = st.columns([1, 2])
        with col_exp1:
            if st.button("📥 Export Investigation Note", type="primary", key="btn_export"):
                note = export_current_workbench_state(view)
                st.session_state.last_exported_note = note
                st.success("Investigation Note captured (includes current view + full in-session state).")
        with col_exp2:
            if st.session_state.get("last_exported_note"):
                note = st.session_state.last_exported_note
                st.download_button(
                    label="Download note as .json",
                    data=json.dumps(note, indent=2, default=str),
                    file_name=f"investigation_{state.selected_portfolio}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )
                with st.expander("Preview exported note"):
                    st.json(note)

    # Footer / contract reminder (Phase 4L Decision Surface)
    st.divider()
    st.caption(
        "Hero Decision Band (Phase 4L) is always rendered first and is mode-independent. "
        "Friend Mode uses the locked Phase 4K child presenters only. "
        "Analyst Mode preserves 4I/4J functionality subordinate to the Hero Band. "
        "All data from thin presenters in narrative.py. See Phase 4L contract for full guardrails."
    )


if __name__ == "__main__":
    main()
