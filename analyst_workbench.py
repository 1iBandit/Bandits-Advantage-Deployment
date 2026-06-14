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

# Force full rebuild - stale build cache workaround 2026-06-14 (Second Guided Question micro-chunk)
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

    state: WorkbenchSessionState = st.session_state.wb_state
    demo: Dict[str, Any] = st.session_state.demo_data

    # --- Sidebar: All flow controls live here (keeps main area focused) ---
    with st.sidebar:
        st.header("Portfolio & Time")

        portfolio_options = ["P001_GROWTH", "P002_PRESERVATION"]
        current_idx = 0 if state.selected_portfolio == "P001_GROWTH" else 1
        new_portfolio = st.selectbox(
            "Active Portfolio",
            portfolio_options,
            index=current_idx,
            key="sb_portfolio",
        )
        if new_portfolio != state.selected_portfolio:
            select_portfolio(state, new_portfolio)
            st.rerun()

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

    # --- Main area ---
    registry, lifecycles, snapshot, ledger, base_weekly = get_current_objects(demo, state.selected_portfolio)

    # === Phase 4L Hero Decision Band (dominant, always visible, mode-independent) ===
    # All data from get_hero_decision_band_data (thin presenter in narrative.py)
    hero = get_hero_decision_band_data(
        state.selected_portfolio, registry, lifecycles, snapshot
    )

    rec = hero["primary_recommendation"]
    is_abstain = hero.get("is_abstaining", False)

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

            continuity_header = "This week’s volatility is similar to periods you’ve found stressful before. Let’s focus on stability."
            hero_framing = "Given your discomfort with drawdowns above 15%, I’m prioritizing stability over action today."
            identity_framing = "I'm guiding you as a BalancedCore investor, with extra focus on protecting your comfort zone during volatility."
            guided_question = "What would help you feel safe staying the course here?"
            guided_rationale = "Avoiding panic-selling during periods like this has historically improved long-term stability for investors like you."
            explain_text = "You’ve been checking short-term changes more frequently today, so I’m foregrounding stability and long-term context. All of your usual details are still available below."
        else:
            continuity_header = None
            hero_framing = None
            identity_framing = None
            guided_question = None
            guided_rationale = None
            explain_text = None

        if continuity_header:
            st.caption(continuity_header)

        if hero_framing:
            st.caption(hero_framing)

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
            st.subheader("️ Identity Card")
            st.caption(identity_card.get("framing", ""))

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
                st.success("Your Friend Profile has been updated. The Identity Card and Guided Question have adapted to your changes. You did this. I’m just helping you see it.")
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
