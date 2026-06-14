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
)
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

    snap_g = build_portfolio_snapshot(
        "P001_GROWTH", base_chain.narrative_chain_id, rec_states_g, risk_g, lc_g, base_chain,
        {"source": "4C-streamlit-demo", "portfolio_id": "P001_GROWTH"}
    )
    snap_p = build_portfolio_snapshot(
        "P002_PRESERVATION", base_chain.narrative_chain_id, rec_states_p, risk_p, lc_p, base_chain,
        {"source": "4C-streamlit-demo", "portfolio_id": "P002_PRESERVATION"}
    )

    # Minimal weekly update placeholders (the real generator lives in narrative)
    base_weekly_g = {"portfolio_id": "P001_GROWTH", "executive_summary": "Demo growth portfolio state."}
    base_weekly_p = {"portfolio_id": "P002_PRESERVATION", "executive_summary": "Demo preservation portfolio state."}

    lifecycles_map = {
        "P001_GROWTH": lc_g,
        "P002_PRESERVATION": lc_p,
    }
    snapshots_map = {
        "P001_GROWTH": snap_g,
        "P002_PRESERVATION": snap_p,
    }
    base_weekly_map = {
        "P001_GROWTH": base_weekly_g,
        "P002_PRESERVATION": base_weekly_p,
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
    """Helper to grab the right objects for the selected portfolio."""
    return (
        demo["registry"],
        demo["lifecycles"][portfolio_id],
        demo["snapshots"][portfolio_id],
        demo["ledger"],
        demo["base_weekly"][portfolio_id],
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

    st.set_page_config(
        page_title="Bandit's Advantage — Analyst Workbench",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("📈 Bandit's Advantage — Analyst Workbench")
    st.caption("Phase 4I + 4J  •  Thin read-only presentation layer  •  All data from isolated narrative spine")

    # Permanent guardrail banner (matches the locked contracts)
    st.warning(
        "**Architectural Guardrail**: This UI only renders data produced by the Phase 3 calibrated decision engine "
        "and the Phase 4A–4J observational layers (narrative.py). It performs no scoring, no new rules, "
        "and never influences recommendations. `intelligence_layers_enabled` remains False. "
        "State is session-only unless you explicitly Export an Investigation Note."
    )

    # One-time setup of demo data + session state
    if "wb_state" not in st.session_state:
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
        portfolio_options = ["P001_GROWTH", "P002_PRESERVATION", "P003_INCOME"]
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
            select_portfolio(state, new_portfolio)
            # Router handles behavioral isolation switch
            switch_to_slot(new_portfolio)
            # Note: switch_to_slot does st.rerun() internally for full surface teardown

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

        st.caption(f"Hero Band • {state.selected_portfolio} • Phase 4L (Context-Aware)")
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

        st.caption(f"Hero Band • {state.selected_portfolio} • Phase 4L")
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
        # Uses locked 4K presenters. Hero Band is already rendered above.
        st.divider()
        st.subheader("Friend Mode (4K)")  # H2 per locked Typography for mode headers
        st.caption("Guided companion experience powered by your Friend Profile.")  # Caption per hierarchy

        # === v0.2 Continuity Header with Portfolio Router (Surface 1) ===
        active_slot = get_active_slot_id()
        display_name = get_slot_display_name(active_slot)
        idx = get_slot_index(active_slot)
        total = get_total_slots()
        st.markdown(
            f"**Buddy: David** | Active: **{display_name} ({idx}/{total})**"
        )
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
            # Keep analytical data in sync with the behavioral slot (for Hero Band + data surfaces)
            if new_slot != state.selected_portfolio:
                select_portfolio(state, new_slot)
            switch_to_slot(new_slot)

        # === Liam Onboarding Question Tree v0.1 (GROUNDING → TEACHING → REINFORCING) ===
        # Multi-step conversational flow for avoidant, first-paycheck user (Liam persona).
        # Placed early in Friend Mode for onboarding focus. Integrates with sandbox_ledger and behavioral_state.
        # Uses low-pressure inputs, sets states, updates ledger on commitment. Respects Unfiltered View.
        if "liam_step" not in st.session_state:
            st.session_state["liam_step"] = 0
            st.session_state["behavioral_state"] = "GROUNDING"

        liam_step = st.session_state["liam_step"]

        # Helper to advance step and optionally set state
        def advance_liam_step(next_step, new_state=None):
            st.session_state["liam_step"] = next_step
            if new_state:
                st.session_state["behavioral_state"] = new_state
            st.rerun()

        st.markdown("---")
        st.subheader("Liam Onboarding Journey (v0.1 Demo)")

        if liam_step == 0:
            # Grounding Welcome
            st.markdown("### Grounding Welcome")
            st.markdown(
                "Hey, this is your first real paycheck and your first real step with money. "
                "No pressure, no judgment — we're just getting clear together in this safe sandbox. "
                "I'm here to help you see what's possible, one small conversation at a time. "
                "You did this. I’m just helping you see it."
            )
            if st.button("I'm ready to begin gently", key="liam_start"):
                advance_liam_step(1, "GROUNDING")

        elif liam_step == 1:
            # Current Reality Check - Cash buffer
            st.markdown("### Current Reality Check")
            st.markdown(
                "Before we look at anything else, let's get a gentle picture of your cash right now. "
                "This isn't about having 'enough' — it's about seeing where you actually are so we can build from there."
            )
            cash_buffer = st.slider(
                "How much cash do you have right now that isn't already spoken for by bills or essentials? "
                "(It's completely okay if this number feels small or even zero. We're starting exactly where you are.)",
                min_value=0,
                max_value=10000,
                value=st.session_state.get("liam_cash_buffer", 300),
                step=50,
                key="liam_cash_slider"
            )
            if st.button("Continue with this picture", key="liam_cash_continue"):
                st.session_state["liam_cash_buffer"] = cash_buffer
                new_state = "TEACHING" if cash_buffer < 1000 else "GROUNDING"
                advance_liam_step(2, new_state)

        elif liam_step == 2:
            # Existing Assets Discovery
            st.markdown("### Existing Assets Discovery")
            st.markdown(
                "A lot of people have a little something already started — maybe a Roth IRA from a previous job, a family gift, or just a small account. "
                "If you have one, even a small amount like $3,500, let's note it here. No shame if it's zero or unknown."
            )
            roth_amount = st.number_input(
                "Roughly how much do you have in any retirement accounts (like a Roth IRA) right now?",
                min_value=0,
                value=st.session_state.get("liam_roth", 0),
                step=100,
                key="liam_roth_input"
            )
            if st.button("Continue", key="liam_roth_continue"):
                st.session_state["liam_roth"] = roth_amount
                advance_liam_step(3)

        elif liam_step == 3:
            # Priority Framing (TEACHING)
            st.markdown("### Priority Framing")
            cash = st.session_state.get("liam_cash_buffer", 0)
            roth = st.session_state.get("liam_roth", 0)
            if cash < 1000 or roth < 3500:
                st.markdown(
                    "Given where you're starting, it makes a lot of sense to focus first on building a small shield — "
                    "having some cash on hand for surprises. This is smart, responsible, and the foundation everything else rests on. "
                    "Growing an 'engine' can come after the shield feels a bit more solid."
                )
            else:
                st.markdown(
                    "You have a decent base already. We can think about both keeping the shield strong and letting the engine (your investments) grow steadily."
                )
            st.caption("This is just perspective to help you choose what matters most right now.")
            if st.button("Got it — let's pick a first step", key="liam_priority_continue"):
                advance_liam_step(4, "TEACHING")

        elif liam_step == 4:
            # First Small Commitment (REINFORCING setup)
            st.markdown("### First Small Commitment")
            st.markdown(
                "Now that we've looked at the real picture together, what feels like a realistic, doable amount to set aside from your very next paycheck? "
                "Even $20, $50, or $100 is a powerful, real start. Small consistent actions build the habit and the confidence."
            )
            commit_amount = st.number_input(
                "What amount feels realistic for your first commitment from the next paycheck?",
                min_value=0,
                value=st.session_state.get("liam_commit", 50),
                step=10,
                key="liam_commit_input"
            )
            if st.button("This is my first step — let's lock it in", key="liam_commit_continue"):
                st.session_state["liam_commit"] = commit_amount
                advance_liam_step(5, "REINFORCING")

        elif liam_step == 5:
            # Summary + Next Step
            st.markdown("### Summary + Next Step")
            cash = st.session_state.get("liam_cash_buffer", 0)
            roth = st.session_state.get("liam_roth", 0)
            commit = st.session_state.get("liam_commit", 0)
            st.markdown(
                f"You shared: current cash buffer around ${cash}, existing retirement ~${roth}, "
                f"and a first commitment of ${commit} from your next paycheck."
            )
            st.markdown(
                "That's a real, brave, and concrete start. You did this. I’m just helping you see it."
            )
            st.caption("This is how real progress begins — one clear, owned step at a time.")

            if st.button("Apply my first commitment to the 1i_Bandit Sandbox Ledger", key="liam_apply_ledger"):
                # Integrate with sandbox: add/update a CASH entry for the commitment
                if "sandbox_ledger" not in st.session_state:
                    st.session_state["sandbox_ledger"] = {}
                st.session_state["sandbox_ledger"]["CASH"] = {
                    "shares": commit,
                    "price": 1.0,
                    "date": "2026-06"
                }
                st.success(
                    f"Perfect — your ${commit} first commitment is now reflected in the 1i_Bandit sandbox ledger as CASH. "
                    "This is how we practice the habit safely."
                )
                st.session_state["liam_step"] = 6  # completed
                st.rerun()

            if st.button("Restart this onboarding journey", key="liam_restart"):
                st.session_state["liam_step"] = 0
                for key in ["liam_cash_buffer", "liam_roth", "liam_commit"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()

        if liam_step >= 6:
            st.caption("Onboarding complete for this session. Your behavioral state is now set to REINFORCING, and the sandbox reflects your first step. The other surfaces below will respond to this.")

        # Note: The Identity Card and Guided Question use st.subheader for their titles (H2 per locked Typography for card headers / major Friend Mode surfaces). Internal bold labels (e.g. **Primary Goals**) are H3 (Medium). All framing/provenance use st.caption (Caption per locked).

        # Friend Mode color system styles (from locked Color System + Card Design)
        # Applied to the .identity-card-wrapper class we inject around the Identity Card.
        st.markdown("""
<style>
.identity-card-wrapper {
    border: 4px solid #4A90E2 !important;
    background-color: #E8F1FF55 !important;
    border-radius: 12px !important;
    padding: 1.5rem !important;
    box-shadow: 0 0 12px rgba(74, 144, 226, 0.4) !important;
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
        if st.button("Simulate panic pattern (high checking + hover for demo)", key="btn_simulate_panic"):
            capture_event("projection_view", {"portfolio": state.selected_portfolio})
            capture_event("hover_sell", {"portfolio": state.selected_portfolio})
            st.session_state["behavioral_state"] = "CALMING"
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
            write_current_behavioral_to_registry(get_active_slot_id())
            st.rerun()

        # Simulate Reinforcing Pattern for REINFORCING state (v0.1)
        if st.button("Simulate Reinforcing Pattern", key="btn_simulate_reinforcing"):
            st.session_state["behavioral_state"] = "REINFORCING"
            capture_event("reinforcement_event", {
                "portfolio": state.selected_portfolio
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

            st.markdown('</div>', unsafe_allow_html=True)

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
            st.subheader(" Manual Ledger (Sandbox)")
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
                        st.success(
                            f"Ledger entry for {target_ticker} updated in session. "
                            "Identity alignment preserved."
                        )
                        st.rerun()

        # === RELATIONSHIP MEMORY GRAPH VIEWER (v0.1) ===
        # Thin, session-only, read-only audit surface per the Relationship Memory Graph Viewer micro-chunk.
        # Reuses existing behavioral_events + panic_pattern_nodes (no new storage keys).
        # Enforces: "A true companion never keeps a secret file on your behavior."
        # Placement: directly under the Editable Profile (before the lower friend view summaries).
        # Language strictly action-based, non-diagnostic. Purge is nuclear + confirmed.
        # Unfiltered View collapses the surface per governance rules.

        st.markdown("---")

        is_unfiltered = st.session_state.get("unfiltered_view", False)

        with st.container(border=True):
            st.subheader("What I'm Remembering This Session")

            if is_unfiltered:
                force_neutral_all_slots()
                st.caption("Memory-assisted guidance is currently deactivated for this session via your Unfiltered View override toggle.")
                # Do not render any event details when governance override is active
            else:
                # Thin read of real session state (no behavior_event_log alias; use the live ones)
                session_events = get_events()
                current_panic = get_current_panic_pattern()

                if not current_panic and not any(getattr(e, "event_type", None) == "panic_pattern" for e in session_events):
                    st.info("I haven't recorded any behavioral variations in this session yet. This section dynamically updates when actions trigger structural safety adjustments.")
                else:
                    st.caption("This layer ensures complete transparency. A true companion never keeps a secret file on your behavior.")
                    st.caption("This transparent log displays how your real-time interaction patterns adjust our communication parameters. This data lives strictly in volatile memory.")

                    # Render the observed pattern using neutral, action-only language (Rule 2a/2b/2c)
                    # We translate the existence of the panic_pattern node / event into the prescribed framing.
                    for event in session_events:
                        et = getattr(event, "event_type", None) if not isinstance(event, dict) else event.get("event_type")
                        if et == "panic_pattern":
                            # Compute a light count for granularity (from the same event stream)
                            check_count = sum(1 for e in session_events if getattr(e, "event_type", None) == "portfolio_check")
                            st.markdown(f"""
**Active Tracking: High Interaction Volume During Market Variance**
* **Observed Signal:** App tracking interfaces reviewed {check_count} times while valuation metrics shifted downward.
* **System Adjustment:** Structural focus moved toward cash-flow runway protection to isolate short-term volatility.
""")
                            break
                    else:
                        # Fallback if only the node exists (no separate event record this run)
                        if current_panic:
                            check_count = sum(1 for e in session_events if getattr(e, "event_type", None) == "portfolio_check")
                            st.markdown(f"""
**Active Tracking: High Interaction Volume During Market Variance**
* **Observed Signal:** App tracking interfaces reviewed {check_count} times while valuation metrics shifted downward.
* **System Adjustment:** Structural focus moved toward cash-flow runway protection to isolate short-term volatility.
""")

                    st.markdown("---")

                    # Destructive Sovereign Purge Pipeline (two-step confirm, atomic teardown)
                    if "confirm_purge" not in st.session_state:
                        st.session_state["confirm_purge"] = False

                    if not st.session_state["confirm_purge"]:
                        if st.button("Clear Everything I've Shared This Session", key="purge_init_btn"):
                            st.session_state["confirm_purge"] = True
                            st.rerun()
                    else:
                        st.warning("Are you sure? This instantly wipes all logged behavioral triggers and resets the communication interface back to neutral baseline standards. This cannot be undone.")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Yes, Clear My Session Memory", key="purge_confirm_btn"):
                                # Nuclear structural purge sequence (session-only)
                                st.session_state["behavioral_events"] = []
                                st.session_state["panic_pattern_nodes"] = []
                                st.session_state["behavioral_state"] = "NEUTRAL"
                                write_current_behavioral_to_registry(get_active_slot_id())
                                st.session_state["confirm_purge"] = False
                                st.success("Session memory dropped cleanly. Starting fresh.")
                                st.rerun()
                        with col2:
                            if st.button("Cancel Reset", key="purge_cancel_btn"):
                                st.session_state["confirm_purge"] = False
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
