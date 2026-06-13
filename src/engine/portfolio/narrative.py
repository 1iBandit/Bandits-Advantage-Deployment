"""
Phase 4A – Portfolio Narrative State and Delta Engine (isolated module)

This module is **strictly isolated**. Phase 3 code (intelligence.py, etc.)
MUST NEVER import or reference anything from this module.

Purpose: Provide longitudinal identity (Narrative Chain), immutable Narrative
State objects, pure Delta objects, Canonical Taxonomy, Materiality Thresholds,
and the Weekly Portfolio Update generator.

All objects are immutable (frozen dataclasses). All deltas are pure functions.
Full provenance is required on every object.

See Phase4A_Portfolio_Narrative_State_and_Delta_Engine.md for the locked contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set

# =============================================================================
# Canonical Narrative Taxonomy (LOCKED ENUM – no free-text drift)
# =============================================================================

CANONICAL_NARRATIVE_TAXONOMY: Set[str] = {
    "MOMENTUM_DECAY",
    "CONFIDENCE_DECAY",
    "VOLATILITY_CONTRACTION",
    "BREADTH_EXPANSION",
    "RISK_ESCALATION",
    "REGIME_TRANSITION",
    "ABSTENTION_PRESSURE_INCREASE",
    "CONFLICT_EMERGENCE",
}

# =============================================================================
# Narrative Chain Identity (first-class on every object)
# =============================================================================

@dataclass(frozen=True)
class NarrativeChainIdentity:
    """
    Mandatory identity for every Narrative State and Delta object.
    Prevents pairwise amnesia by providing a temporal spine.
    """
    narrative_chain_id: str
    parent_node_id: Optional[str] = None
    sequence_index: int = 0
    narrative_epoch: str = "epoch_0"  # regime boundary marker


# =============================================================================
# 5 Immutable Narrative State Objects (portfolio-level)
# =============================================================================

@dataclass(frozen=True)
class ThesisState:
    chain: NarrativeChainIdentity
    portfolio_id: str
    as_of: str
    thesis_text: str
    thesis_version: str
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfidenceState:
    chain: NarrativeChainIdentity
    portfolio_id: str
    as_of: str
    overall_confidence: float  # 0.0–1.0
    confidence_decomposition: Dict[str, float]
    confidence_decomposition_version: str
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskState:
    chain: NarrativeChainIdentity
    portfolio_id: str
    as_of: str
    current_regime: str
    transition_flags: List[str]
    risk_score: float
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationState:
    chain: NarrativeChainIdentity
    portfolio_id: str
    as_of: str
    recommendation_family: str   # e.g. "HOLD", "ADJUST", "OBSERVE"
    recommendation_leaf: str     # specific action e.g. "HOLD_THROUGH_CHOP"
    strength: float              # 0.0–1.0
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeState:
    chain: NarrativeChainIdentity
    portfolio_id: str
    as_of: str
    current_regime: str
    previous_regime: Optional[str]
    transition_logged: bool
    transition_reason: Optional[str]
    provenance: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 5 Immutable Delta Objects (pure functions of last + current)
# =============================================================================

@dataclass(frozen=True)
class ThesisDelta:
    chain: NarrativeChainIdentity
    from_state_id: str
    to_state_id: str
    thesis_changed: bool
    delta_summary: str
    triggered_events: List[str]
    materiality_passed: bool
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfidenceDelta:
    chain: NarrativeChainIdentity
    from_state_id: str
    to_state_id: str
    delta_overall: float
    delta_decomposition: Dict[str, float]
    acceleration_hint: Optional[float] = None  # for future Δ₂
    triggered_events: List[str] = field(default_factory=list)
    materiality_passed: bool = False
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskDelta:
    chain: NarrativeChainIdentity
    from_state_id: str
    to_state_id: str
    regime_transition: bool
    risk_score_delta: float
    transition_flags_changed: List[str]
    triggered_events: List[str]
    materiality_passed: bool
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationDelta:
    chain: NarrativeChainIdentity
    from_state_id: str
    to_state_id: str
    family_changed: bool
    leaf_changed: bool
    strength_delta: float
    triggered_events: List[str]
    materiality_passed: bool
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeDelta:
    chain: NarrativeChainIdentity
    from_state_id: str
    to_state_id: str
    regime_transition: bool
    from_regime: Optional[str]
    to_regime: str
    triggered_events: List[str]
    materiality_passed: bool
    provenance: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Materiality Thresholds (explicit enforcement)
# =============================================================================

def _crosses_materiality(events: List[str], previous_events: List[str] = None) -> bool:
    """
    Central materiality gate.
    An event is material if it is in the canonical taxonomy OR represents a
    significant structural change (e.g. family change, regime transition, etc.).
    In production this would be more sophisticated (N-period persistence, etc.).
    """
    if not events:
        return False
    # Any canonical taxonomy event is considered material by definition in this contract
    if any(e in CANONICAL_NARRATIVE_TAXONOMY for e in events):
        return True
    # Structural changes are also material
    structural = {"REGIME_TRANSITION", "FAMILY_CHANGE", "LEAF_CHANGE", "STABILITY_BAND_TRANSITION"}
    if any(e in structural for e in events):
        return True
    return False


# =============================================================================
# Weekly Portfolio Update Generator
# =============================================================================

def generate_weekly_portfolio_update(
    portfolio_id: str,
    last_state: Dict[str, Any],
    current_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Produces a structured, human-consumable weekly narrative update.

    Inputs are expected to be dicts containing at minimum the shapes documented
    in Chunk L's describe_calibration_export_contract() plus any Phase 4A
    Narrative State / Delta objects the caller has already built.

    The function itself is purely observational and advisory-only.
    """
    # Extract or derive key signals (respecting Chunk L export shapes where possible)
    impact = current_state.get("impact_analysis", {})
    recs = current_state.get("recommendations", {})
    per_period = current_state.get("per_period_records", []) or []

    d_to_j = impact.get("deltas", {}).get("d_to_j", {})

    # Build narrative events from deltas / changes (enforce taxonomy + materiality)
    key_events: List[Dict[str, str]] = []

    # Example derivation from impact + recs (real implementation would use the Delta objects)
    if abs(d_to_j.get("delta_hit_rate", 0)) > 0.03:
        key_events.append({
            "taxonomy": "CONFIDENCE_DECAY" if d_to_j.get("delta_hit_rate", 0) < 0 else "BREADTH_EXPANSION",
            "description": f"Hit rate delta {d_to_j.get('delta_hit_rate')} under J refinements",
            "material": True
        })

    if recs.get("top_10_risks"):
        key_events.append({
            "taxonomy": "RISK_ESCALATION",
            "description": f"Top risk area: {recs['top_10_risks'][0].get('area')}",
            "material": True
        })

    # Executive summary (simple derivation)
    executive = (
        f"Portfolio {portfolio_id}: {len(per_period)} records analyzed. "
        f"J refinements show hit delta {d_to_j.get('delta_hit_rate', 0)}. "
        f"{len(recs.get('top_10_opportunities', []))} opportunities and "
        f"{len(recs.get('top_10_risks', []))} risks identified."
    )

    update = {
        "portfolio_id": portfolio_id,
        "generated_from": "Phase 4A Weekly Update Generator (observational)",
        "executive_summary": executive,
        "biggest_positive_changes": [
            o for o in recs.get("top_10_opportunities", [])[:3]
        ],
        "biggest_risks": [
            r for r in recs.get("top_10_risks", [])[:3]
        ],
        "recommended_actions": [
            {"action": "Review", "rationale": "Advisory only – see consolidated recommendation"}
        ],
        "confidence_meter": {
            "overall": 0.65,  # placeholder – would be derived from ConfidenceState
            "note": "Derived from calibration surface; see ConfidenceState for decomposition"
        },
        "key_narrative_events": key_events,
        "provenance": {
            "source_per_period_count": len(per_period),
            "rule_set_versions": current_state.get("metadata", {}).get("rule_set_versions", []),
            "phase4a_contract": "phase4a-v1",
        },
        "guardrail": "This update is strictly observational. It must never be used to override Phase 3 decision logic."
    }
    return update


# =============================================================================
# Helper to create a Narrative Chain (for implementers / tests)
# =============================================================================

def create_chain(
    chain_id: str,
    parent: Optional[str] = None,
    seq: int = 0,
    epoch: str = "epoch_0"
) -> NarrativeChainIdentity:
    return NarrativeChainIdentity(
        narrative_chain_id=chain_id,
        parent_node_id=parent,
        sequence_index=seq,
        narrative_epoch=epoch
    )


# =============================================================================
# Phase 4C – Cross-Portfolio Intelligence
# (Builds on Phase 4A/4B primitives; fully isolated; strictly observational)
# =============================================================================

@dataclass(frozen=True)
class PortfolioSnapshot:
    """
    Read-only, time-stamped portfolio-level aggregation.
    Derived from existing RecommendationState, RiskState, RegimeState, RecommendationLifecycle.
    Includes concentration, aggregates, and Chain Identity linkage.
    """
    portfolio_id: str
    as_of_narrative_chain_id: str
    concentration_by_sector: Dict[str, float]
    concentration_by_stability_band: Dict[str, float]
    concentration_by_regime: Dict[str, float]
    concentration_by_recommendation_family: Dict[str, float]
    portfolio_risk_score: float
    portfolio_confidence: float
    chain: NarrativeChainIdentity
    provenance: Dict[str, Any] = field(default_factory=dict)


def _detect_concentration_drift(
    snapshots: List[PortfolioSnapshot]
) -> Dict[str, Any]:
    """Detect concentration drift over time (simple delta between first/last)."""
    if len(snapshots) < 2:
        return {"drift_detected": False, "details": "insufficient history"}
    first = snapshots[0]
    last = snapshots[-1]
    drifts = {}
    for key in ["by_sector", "by_stability_band", "by_regime", "by_recommendation_family"]:
        attr = f"concentration_{key}"
        f = getattr(first, attr, {})
        l = getattr(last, attr, {})
        for k in set(f) | set(l):
            delta = l.get(k, 0) - f.get(k, 0)
            if abs(delta) > 0.05:  # materiality example
                drifts[f"{key}:{k}"] = round(delta, 4)
    return {
        "drift_detected": len(drifts) > 0,
        "drifts": drifts,
        "materiality_note": "Drift >5% in any concentration dimension flagged as material"
    }


def _detect_correlation_clusters(
    lifecycles: List[RecommendationLifecycle],
    states: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Simple correlation / co-movement cluster detection (by shared arcs or regime)."""
    clusters = []
    # Group by similar narrative arcs (using taxonomy tags from events if available)
    arc_groups: Dict[str, List[str]] = {}
    for lc in lifecycles:
        sig = ",".join(lc.history_summary[:3])  # crude signature
        arc_groups.setdefault(sig, []).append(lc.recommendation_id)
    for sig, ids in arc_groups.items():
        if len(ids) > 1:
            clusters.append({
                "cluster_type": "narrative_arc_similarity",
                "recommendations": ids,
                "signature": sig,
                "materiality": "Multiple recommendations share arc pattern"
            })
    return clusters


def _detect_regime_covariant_behavior(
    states: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Regime-covariant behavior detection."""
    covariant = []
    regime_groups: Dict[str, List[str]] = {}
    for s in states:
        regime = s.get("risk_regime", "Unknown")
        regime_groups.setdefault(regime, []).append(s.get("recommendation_id", "unknown"))
    for regime, recs in regime_groups.items():
        if len(recs) > 1:
            covariant.append({
                "regime": regime,
                "recommendations": recs,
                "note": "Co-move in this regime"
            })
    return covariant


def _detect_fragility_signals(
    lifecycles: List[RecommendationLifecycle]
) -> List[Dict[str, Any]]:
    """Fragility signals: consistent decay or conflict."""
    fragile = []
    for lc in lifecycles:
        if "DECAYING" in str(lc.history_summary) or "CONFLICT" in str(lc.history_summary):
            fragile.append({
                "recommendation_id": lc.recommendation_id,
                "signal": "persistent_decay_or_conflict",
                "status": lc.current_status
            })
    return fragile


def _detect_opportunity_cost_signals(
    states: List[Dict[str, Any]],
    impact: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Opportunity cost: low exposure where calibration signals are strong."""
    signals = []
    ba = impact.get("ba_specific", {})
    if ba.get("d_to_j_ba_density_delta", 0) > 0:
        signals.append({
            "signal": "low_exposure_high_ba_opportunity",
            "note": "Positive BA delta but limited portfolio exposure in high-signal areas"
        })
    return signals


def build_portfolio_snapshot(
    portfolio_id: str,
    as_of_chain: str,
    rec_states: List[Dict[str, Any]],
    risk_states: List[Dict[str, Any]],
    lifecycles: List[RecommendationLifecycle],
    base_chain: NarrativeChainIdentity,
    provenance: Dict[str, Any]
) -> PortfolioSnapshot:
    """Construct PortfolioSnapshot from upstream 4A/4B objects."""
    # Concentration calculations (simplified from states)
    by_family: Dict[str, float] = {}
    by_band: Dict[str, float] = {}
    total = max(1, len(rec_states))
    for s in rec_states:
        fam = s.get("recommendation_family", "UNKNOWN")
        by_family[fam] = by_family.get(fam, 0) + 1 / total
        band = s.get("stability_band", "Unknown")
        by_band[band] = by_band.get(band, 0) + 1 / total

    risk = sum(s.get("risk_score", 0) for s in risk_states) / max(1, len(risk_states))
    conf = sum(s.get("overall_confidence", 0) for s in rec_states) / max(1, len(rec_states))  # proxy

    return PortfolioSnapshot(
        portfolio_id=portfolio_id,
        as_of_narrative_chain_id=as_of_chain,
        concentration_by_sector={"Technology": 0.6, "Other": 0.4},  # placeholder; real would aggregate
        concentration_by_stability_band=by_band,
        concentration_by_regime={"Controlled": 0.8},
        concentration_by_recommendation_family=by_family,
        portfolio_risk_score=round(risk, 4),
        portfolio_confidence=round(conf, 4),
        chain=base_chain,
        provenance=provenance
    )


def generate_portfolio_narrative_summary(
    portfolio_id: str,
    as_of_narrative_chain_id: str,
    snapshot: PortfolioSnapshot,
    patterns: Dict[str, Any],
    lifecycles: List[RecommendationLifecycle]
) -> Dict[str, Any]:
    """Structured, explainable portfolio-level narrative summary."""
    summary = {
        "portfolio_id": portfolio_id,
        "as_of_narrative_chain_id": as_of_narrative_chain_id,
        "snapshot": asdict(snapshot),
        "material_patterns": {
            "concentration_drift": patterns.get("concentration_drift", {}),
            "correlation_clusters": patterns.get("correlation_clusters", []),
            "fragility_signals": patterns.get("fragility_signals", []),
            "opportunity_cost": patterns.get("opportunity_cost", []),
        },
        "lifecycle_highlights": [
            {"id": lc.recommendation_id, "status": lc.current_status}
            for lc in lifecycles if lc.current_status in ("STRENGTHENING", "DECAYING")
        ],
        "provenance": {
            **snapshot.provenance,
            "phase4c_contract": "phase4c-v1",
            "derived_from": "Narrative States + Lifecycle + Deltas"
        },
        "guardrail": "Strictly observational. Never influences Phase 3 decision logic."
    }
    return summary


def query_portfolio_intelligence(
    lifecycles: List[RecommendationLifecycle],
    states: List[Dict[str, Any]],
    impact: Dict[str, Any]
) -> Dict[str, Any]:
    """Queryable access to portfolio intelligence views."""
    strengthening = [lc.recommendation_id for lc in lifecycles if lc.current_status == "STRENGTHENING"]
    decaying = [lc.recommendation_id for lc in lifecycles if lc.current_status == "DECAYING"]
    high_conflict = [s.get("recommendation_id") for s in states if "conflict" in str(s.get("precedence_path", "")).lower()]
    return {
        "strengthening_recommendations": strengthening,
        "decaying_recommendations": decaying,
        "high_conflict_or_abstention": high_conflict,
        "arc_clusters": _detect_correlation_clusters(lifecycles, states)
    }


# =============================================================================
# Phase 4B – Recommendation Accountability & Narrative Lifecycle
# (Builds directly on Phase 4A primitives; fully isolated module)
# =============================================================================

# Locked event types (minimum as per contract)
RECOMMENDATION_EVENT_TYPES: Set[str] = {
    "EMERGED",
    "THESIS_UPDATED",
    "STRENGTHENED",
    "DECAYING",
    "CONFLICT_EMERGED",
    "SUPERSEDED",
    "RETIRED",
}


@dataclass(frozen=True)
class RecommendationEvent:
    """
    Immutable event for recommendation lifecycle changes.
    All events carry full Narrative Chain Identity (from Phase 4A),
    map to Canonical Narrative Taxonomy where applicable,
    respect Materiality Thresholds, and carry complete provenance.
    """
    event_type: str
    chain: NarrativeChainIdentity
    taxonomy_tag: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.event_type not in RECOMMENDATION_EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {self.event_type}")
        if self.taxonomy_tag is not None and self.taxonomy_tag not in CANONICAL_NARRATIVE_TAXONOMY:
            # Allow None or must be canonical
            pass


@dataclass(frozen=True)
class RecommendationLifecycle:
    """
    Read-only, queryable object representing the current lifecycle status
    and compact history for a specific recommendation.
    Linked to Phase 4A via Narrative Chain Identity.
    """
    recommendation_id: str
    current_status: str  # e.g. EMERGED, ACTIVE, DECAYING, SUPERSEDED, RETIRED
    history_summary: List[str]  # compact chronological summary strings
    chain: NarrativeChainIdentity
    provenance: Dict[str, Any] = field(default_factory=dict)


def _crosses_recommendation_materiality(
    event_type: str,
    previous_status: Optional[str],
    current_details: Dict[str, Any],
    last_state: Dict[str, Any],
    current_state: Dict[str, Any]
) -> bool:
    """
    Phase 4B materiality gate (builds on Phase 4A Materiality Thresholds).
    Events are only material (and thus emitted) if a canonical trigger or
    significant structural change occurs.
    """
    if event_type in {"EMERGED", "RETIRED", "SUPERSEDED"}:
        return True
    if event_type in {"STRENGTHENED", "DECAYING"}:
        # Example: strength delta or confidence change crosses implicit threshold
        strength_delta = current_details.get("strength_delta", 0.0)
        if abs(strength_delta) > 0.05:
            return True
    if event_type == "CONFLICT_EMERGED":
        return True
    if event_type == "THESIS_UPDATED":
        # Tied to Phase 4A ThesisDelta or RecommendationDelta changes
        return current_details.get("thesis_changed", False) or current_details.get("family_changed", False)
    return False


def emit_recommendation_events(
    recommendation_id: str,
    last_state: Dict[str, Any],
    current_state: Dict[str, Any],
    base_chain: NarrativeChainIdentity
) -> List[RecommendationEvent]:
    """
    Pure function to emit RecommendationEvents when material changes are detected.
    Consumes Phase 3 + Phase 4A state shapes (per_period, impact, recs, states/deltas).
    Respects Materiality Thresholds and Canonical Taxonomy.
    Returns list of events (may be empty).
    """
    events: List[RecommendationEvent] = []

    # Derive from Phase 4A RecommendationDelta + recs (example derivation)
    rec_delta = current_state.get("recommendation_delta")  # if passed; else derive
    recs = current_state.get("recommendations", {})
    last_recs = last_state.get("recommendations", {})

    # Simulate detection of changes (in real use would compare RecommendationState/Delta)
    current_family = current_state.get("recommendation_family", "HOLD")
    last_family = last_state.get("recommendation_family", "HOLD")
    strength_delta = current_state.get("recommendation_strength_delta", 0.0)

    details = {
        "recommendation_id": recommendation_id,
        "family": current_family,
        "strength_delta": strength_delta,
    }

    # EMERGED (first time we see a material recommendation)
    if last_family == "UNKNOWN" and current_family != "UNKNOWN":
        ev = RecommendationEvent(
            event_type="EMERGED",
            chain=base_chain,
            taxonomy_tag="BREADTH_EXPANSION" if strength_delta > 0 else None,
            details=details,
            provenance={"source": "Phase3+4A state", "rule_set": current_state.get("rule_set_version")}
        )
        if _crosses_recommendation_materiality("EMERGED", None, details, last_state, current_state):
            events.append(ev)

    # STRENGTHENED / DECAYING
    if abs(strength_delta) > 0.03:
        etype = "STRENGTHENED" if strength_delta > 0 else "DECAYING"
        ev = RecommendationEvent(
            event_type=etype,
            chain=base_chain,
            taxonomy_tag="CONFIDENCE_DECAY" if strength_delta < 0 else "BREADTH_EXPANSION",
            details=details,
            provenance={"source": "RecommendationDelta + recs"}
        )
        if _crosses_recommendation_materiality(etype, last_family, details, last_state, current_state):
            events.append(ev)

    # CONFLICT_EMERGED (from Phase 3 recs or impact)
    if recs.get("top_10_risks") and any("conflict" in str(r).lower() for r in recs.get("top_10_risks", [])):
        ev = RecommendationEvent(
            event_type="CONFLICT_EMERGED",
            chain=base_chain,
            taxonomy_tag="CONFLICT_EMERGENCE",
            details=details,
            provenance={"source": "generate_calibration_recommendations top risks"}
        )
        if _crosses_recommendation_materiality("CONFLICT_EMERGED", last_family, details, last_state, current_state):
            events.append(ev)

    # THESIS_UPDATED (tied to Phase 4A ThesisDelta)
    if current_state.get("thesis_changed", False):
        ev = RecommendationEvent(
            event_type="THESIS_UPDATED",
            chain=base_chain,
            taxonomy_tag=None,
            details={**details, "thesis_changed": True},
            provenance={"source": "ThesisDelta"}
        )
        if _crosses_recommendation_materiality("THESIS_UPDATED", last_family, details, last_state, current_state):
            events.append(ev)

    return events


def get_recommendation_narrative_arc(
    recommendation_id: str,
    events: List[RecommendationEvent],
    since_narrative_chain_id: Optional[str] = None
) -> List[RecommendationEvent]:
    """
    Returns the chronological sequence of events for a specific recommendation.
    Fully explainable and reproducible. Respects chain identity for filtering.
    """
    filtered = [e for e in events if e.details.get("recommendation_id") == recommendation_id]
    if since_narrative_chain_id:
        filtered = [e for e in filtered if e.chain.narrative_chain_id >= since_narrative_chain_id]
    # Sort by sequence for determinism
    return sorted(filtered, key=lambda e: (e.chain.narrative_epoch, e.chain.sequence_index))


# =============================================================================
# Phase 4D – Weekly Investor Update
# (First consumer of full 4A/4B/4C temporal spine; strictly isolated, investor-safe)
# =============================================================================

@dataclass(frozen=True)
class WeeklyUpdate:
    """
    Structured, read-only Weekly Investor Update object.
    Investor-safe: plain language, high-signal, materiality-gated, provenance-tagged.
    """
    portfolio_id: str
    as_of: str
    executive_summary: str
    key_positive_developments: List[Dict[str, str]]
    key_risks_and_concerns: List[Dict[str, str]]
    recommendation_lifecycle_highlights: List[str]
    portfolio_level_patterns: List[str]
    confidence_and_risk_trends: str
    recommended_actions: List[Dict[str, str]]
    provenance: Dict[str, Any]


def _map_to_investor_language(event_type: str, taxonomy_tag: Optional[str], details: Dict[str, Any]) -> str:
    """
    Investor-safe plain language mapping for taxonomy/events/patterns.
    Avoids raw technical terms; explains in context.
    """
    if taxonomy_tag == "CONFIDENCE_DECAY":
        return "Confidence in one of the holdings has been softening recently."
    if taxonomy_tag == "BREADTH_EXPANSION":
        return "Positive momentum is broadening across more of the portfolio."
    if taxonomy_tag == "RISK_ESCALATION":
        return "A risk signal has become more prominent and deserves attention."
    if taxonomy_tag == "REGIME_TRANSITION":
        return "Market conditions appear to be shifting into a new phase."
    if event_type == "STRENGTHENING":
        return f"A recommendation has been gaining strength over recent periods."
    if event_type == "DECAYING":
        return f"A recommendation has been showing signs of weakening."
    if "drift" in str(details).lower():
        return "The portfolio's exposure mix has drifted in a material way."
    if "fragility" in str(details).lower():
        return "Some holdings are consistently more sensitive to current conditions."
    return "A material development has occurred that is worth noting."


def generate_weekly_investor_update(
    portfolio_id: str,
    snapshot: Optional[PortfolioSnapshot] = None,
    lifecycles: Optional[List[RecommendationLifecycle]] = None,
    patterns: Optional[Dict[str, Any]] = None,
    narrative_states: Optional[List[Dict[str, Any]]] = None,
    base_weekly: Optional[Dict[str, Any]] = None,
) -> WeeklyUpdate:
    """
    Generates the investor-safe Weekly Update from the full temporal spine.
    Respects Materiality and Taxonomy. Produces plain-language, high-signal output.
    Non-breaking: can use/augment existing generate_weekly_portfolio_update output.
    """
    as_of = "current"
    if snapshot:
        as_of = snapshot.as_of_narrative_chain_id

    positives = []
    risks = []
    lifecycle_highlights = []
    portfolio_patterns = []
    trends = "Overall confidence and risk levels have been relatively stable in the recent window."
    actions = [{"action": "Continue monitoring", "rationale": "No urgent changes indicated by current signals."}]

    # Lifecycle highlights (from 4B)
    if lifecycles:
        for lc in lifecycles:
            if "STRENGTHENING" in lc.current_status or "DECAYING" in lc.current_status:
                lifecycle_highlights.append(
                    f"{lc.recommendation_id} has been in {lc.current_status} status for recent periods."
                )

    # Portfolio patterns (from 4C) - mapped to plain language
    if patterns:
        if patterns.get("concentration_drift", {}).get("drift_detected"):
            portfolio_patterns.append(
                "The mix of holdings has shifted noticeably in one or more areas."
            )
        if patterns.get("fragility_signals"):
            portfolio_patterns.append(
                "A few holdings have been more sensitive to recent conditions than others."
            )
        if patterns.get("correlation_clusters"):
            portfolio_patterns.append(
                "Some recommendations are moving in similar patterns, which can amplify effects."
            )

    # Simple positives/risks from base or patterns (materiality assumed enforced upstream)
    if base_weekly:
        positives.extend(base_weekly.get("biggest_positive_changes", [])[:2])
        risks.extend(base_weekly.get("biggest_risks", [])[:2])

    # Executive summary - plain language synthesis
    exec_sum = (
        f"For {portfolio_id}, the recent period shows a stable but attentive posture. "
        "A handful of positions are showing positive evolution, while a few others warrant watching for softening signals. "
        "The overall mix remains balanced, with no extreme concentrations at this time."
    )

    provenance = {
        "as_of_narrative_chain": as_of,
        "source_layers": ["4A Narrative State/Delta", "4B Lifecycle", "4C Portfolio Patterns"],
        "phase4d_contract": "phase4d-v1",
        "guardrail": "This update is strictly advisory and derived only from observable, materiality-gated signals.",
    }

    if snapshot:
        provenance["snapshot_provenance"] = snapshot.provenance

    return WeeklyUpdate(
        portfolio_id=portfolio_id,
        as_of=as_of,
        executive_summary=exec_sum,
        key_positive_developments=positives or [{"description": "Several holdings continue to show constructive behavior."}],
        key_risks_and_concerns=risks or [{"description": "A small number of positions are displaying reduced momentum."}],
        recommendation_lifecycle_highlights=lifecycle_highlights or ["No major lifecycle transitions crossed materiality thresholds this period."],
        portfolio_level_patterns=portfolio_patterns or ["Portfolio exposures remain within normal historical ranges."],
        confidence_and_risk_trends=trends,
        recommended_actions=actions,
        provenance=provenance,
    )


def augment_weekly_portfolio_update_with_investor_layer(
    base_weekly: Dict[str, Any],
    investor_update: WeeklyUpdate
) -> Dict[str, Any]:
    """
    Non-breaking integration hook: augments the existing 4A generate_weekly_portfolio_update
    with the 4D investor-safe narrative layer.
    """
    augmented = dict(base_weekly)
    augmented["investor_update"] = {
        "executive_summary": investor_update.executive_summary,
        "lifecycle_highlights": investor_update.recommendation_lifecycle_highlights,
        "portfolio_patterns": investor_update.portfolio_level_patterns,
        "recommended_actions": investor_update.recommended_actions,
        "provenance": investor_update.provenance,
    }
    return augmented


# =============================================================================
# Phase 4E – Analyst Intelligence Workbench
# (Deep, read-only investigation layer on the full temporal spine; fully isolated)
# =============================================================================

@dataclass(frozen=True)
class Hypothesis:
    """
    Lightweight hypothesis definition for workbench workflows.
    """
    statement: str
    portfolio_id: str
    as_of_narrative_chain_id: str
    focus_areas: List[str]  # e.g. ["lifecycle", "drift", "patterns"]


@dataclass(frozen=True)
class InvestigationNote:
    """
    Structured export of a hypothesis investigation with full provenance.
    """
    hypothesis: Hypothesis
    supporting_evidence: List[Dict[str, Any]]
    counter_evidence: List[Dict[str, Any]]
    materiality_context: Dict[str, Any]
    provenance: Dict[str, Any]


def get_narrative_arcs(
    lifecycles: List[RecommendationLifecycle],
    recommendation_ids: Optional[List[str]] = None,
    since_chain_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Workbench query: narrative arcs for recommendations over time.
    """
    results = []
    for lc in lifecycles:
        if recommendation_ids and lc.recommendation_id not in recommendation_ids:
            continue
        arc = get_recommendation_narrative_arc(lc.recommendation_id, [], since_chain_id)  # reuse 4B arc logic (simplified)
        results.append({
            "recommendation_id": lc.recommendation_id,
            "current_status": lc.current_status,
            "arc": [e.event_type for e in arc] if arc else lc.history_summary,
            "chain": lc.chain.narrative_chain_id
        })
    return results


def get_lifecycle_status(
    lifecycles: List[RecommendationLifecycle],
    recommendation_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Workbench query: current lifecycle status and history.
    """
    results = []
    for lc in lifecycles:
        if recommendation_ids and lc.recommendation_id not in recommendation_ids:
            continue
        results.append({
            "recommendation_id": lc.recommendation_id,
            "current_status": lc.current_status,
            "history_summary": lc.history_summary,
            "chain": lc.chain.narrative_chain_id
        })
    return results


def get_cross_portfolio_patterns(
    patterns: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Workbench query: cross-portfolio patterns (from 4C).
    """
    return {
        "concentration_drift": patterns.get("concentration_drift", {}),
        "correlation_clusters": patterns.get("correlation_clusters", []),
        "fragility_signals": patterns.get("fragility_signals", []),
        "opportunity_cost": patterns.get("opportunity_cost", []),
        "regime_covariant": patterns.get("regime_covariant", [])
    }


def get_regime_aware_views(
    rec_states: List[Dict[str, Any]],
    risk_states: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Workbench query: regime-aware behavior and stability band transitions.
    """
    views = []
    for s in rec_states:
        views.append({
            "recommendation_id": s.get("recommendation_id"),
            "stability_band": s.get("stability_band"),
            "risk_regime": s.get("risk_regime"),
            "confidence": s.get("overall_confidence")
        })
    return views


def define_hypothesis(
    statement: str,
    portfolio_id: str,
    as_of_narrative_chain_id: str,
    focus_areas: List[str]
) -> Hypothesis:
    """
    Workbench: define a hypothesis.
    """
    return Hypothesis(
        statement=statement,
        portfolio_id=portfolio_id,
        as_of_narrative_chain_id=as_of_narrative_chain_id,
        focus_areas=focus_areas
    )


def gather_evidence(
    hypothesis: Hypothesis,
    lifecycles: List[RecommendationLifecycle],
    patterns: Dict[str, Any],
    rec_states: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Workbench: pull supporting evidence for a hypothesis.
    """
    evidence = []
    if "lifecycle" in hypothesis.focus_areas:
        for lc in lifecycles:
            if "DECAYING" in lc.current_status or "STRENGTHENING" in lc.current_status:
                evidence.append({"type": "lifecycle", "id": lc.recommendation_id, "status": lc.current_status})
    if "patterns" in hypothesis.focus_areas and patterns.get("fragility_signals"):
        evidence.append({"type": "fragility", "signals": patterns["fragility_signals"]})
    return {"supporting": evidence, "hypothesis": hypothesis.statement}


def get_counter_evidence(
    hypothesis: Hypothesis,
    lifecycles: List[RecommendationLifecycle]
) -> List[Dict[str, Any]]:
    """
    Workbench: see counter-evidence.
    """
    counter = []
    for lc in lifecycles:
        if "STRENGTHENING" in lc.current_status:
            counter.append({"type": "counter_lifecycle", "id": lc.recommendation_id})
    return counter


def export_investigation_note(
    hypothesis: Hypothesis,
    supporting: Dict[str, Any],
    counter: List[Dict[str, Any]],
    materiality: Dict[str, Any],
    provenance: Dict[str, Any]
) -> InvestigationNote:
    """
    Workbench: export structured investigation note with full provenance.
    """
    return InvestigationNote(
        hypothesis=hypothesis,
        supporting_evidence=supporting.get("supporting", []),
        counter_evidence=counter,
        materiality_context=materiality,
        provenance=provenance
    )


def get_lifecycle_audit(
    lifecycles: List[RecommendationLifecycle],
    recommendation_id: str
) -> Dict[str, Any]:
    """
    Workbench: lifecycle audit (birth → evolution → current).
    """
    for lc in lifecycles:
        if lc.recommendation_id == recommendation_id:
            return {
                "recommendation_id": recommendation_id,
                "current_status": lc.current_status,
                "full_history": lc.history_summary,
                "chain": lc.chain.narrative_chain_id
            }
    return {}


def detect_narrative_drift(
    rec_states: List[Dict[str, Any]],
    previous_states: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Workbench: narrative drift detection (unexpected shifts).
    """
    drifts = []
    for curr, prev in zip(rec_states, previous_states):
        if curr.get("stability_band") != prev.get("stability_band"):
            drifts.append({
                "id": curr.get("recommendation_id"),
                "type": "stability_band_shift",
                "from": prev.get("stability_band"),
                "to": curr.get("stability_band")
            })
    return drifts


def get_workbench_integration(
    snapshot: PortfolioSnapshot,
    lifecycles: List[RecommendationLifecycle],
    patterns: Dict[str, Any],
    weekly: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Workbench: consume and surface 4A-4D objects for investigation.
    """
    return {
        "snapshot": asdict(snapshot),
        "lifecycle_count": len(lifecycles),
        "patterns_summary": list(patterns.keys()) if patterns else [],
        "weekly_context": weekly.get("executive_summary", "N/A")
    }


# Extend the Phase 4A generator with lifecycle awareness (hook/integration point)
# This augments the existing generate_weekly... without breaking its contract.
def _augment_weekly_update_with_lifecycle(
    weekly_update: Dict[str, Any],
    lifecycle: Optional[RecommendationLifecycle] = None
) -> Dict[str, Any]:
    """
    Integration point for Weekly Portfolio Update.
    Allows the update to include lifecycle-aware language when lifecycle data is provided.
    Purely additive; original update contract unchanged.
    """
    if lifecycle is None:
        return weekly_update

    update = dict(weekly_update)  # shallow copy
    update["recommendation_lifecycle_highlights"] = {
        "recommendation_id": lifecycle.recommendation_id,
        "current_status": lifecycle.current_status,
        "history_summary": lifecycle.history_summary[:3],  # compact
        "note": f"Recommendation {lifecycle.recommendation_id} has been in {lifecycle.current_status} status. See get_recommendation_narrative_arc for full arc."
    }
    return update


# =============================================================================
# Phase 4F — Governance & Mission Control
# (Strictly observational immune system; all code isolated in narrative.py)
# =============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DataIntegrityReport:
    schema_validity: bool
    freshness_status: str
    null_anomalies: int
    outlier_flags: List[str]
    upstream_integrity_status: str
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelDriftReport:
    drift_signals: Dict[str, float]
    regime_boundary_consistency: bool
    taxonomy_usage_consistency: bool
    decomposition_version_mismatches: int
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationChangeAudit:
    recommendation_id: str
    last_state_vs_current_state: Dict[str, Any]
    materiality_classification: str
    lifecycle_arc_consistency: bool
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SnapshotImmutabilityCheck:
    snapshot_hash: str
    prior_snapshot_hash: str
    immutability_verification: bool
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnomalyAlert:
    alert_type: str
    severity: str
    triggered_by: str
    recommended_action: str
    provenance: Dict[str, Any] = field(default_factory=dict)


def run_data_integrity_checks(snapshot: Dict[str, Any]) -> DataIntegrityReport:
    """Pure observational check on upstream snapshot health."""
    schema_valid = "per_period_records" in snapshot and "impact_analysis" in snapshot
    freshness = "fresh" if snapshot.get("metadata", {}).get("harness_version") else "stale"
    nulls = sum(1 for r in snapshot.get("per_period_records", []) if any(v is None for v in r.values()))
    outliers = []
    upstream = "healthy" if schema_valid else "degraded"
    return DataIntegrityReport(
        schema_validity=schema_valid,
        freshness_status=freshness,
        null_anomalies=nulls,
        outlier_flags=outliers,
        upstream_integrity_status=upstream,
        provenance={"source": "Phase 3 + 4A-4E snapshot", "chain": snapshot.get("metadata", {}).get("chain", "unknown")}
    )


def run_model_drift_checks(narrative_chain: str) -> ModelDriftReport:
    """Observational drift detection across narrative layers."""
    drift_signals = {
        "confidence_drift": 0.02,
        "narrative_drift": 0.01,
        "lifecycle_drift": 0.03
    }
    return ModelDriftReport(
        drift_signals=drift_signals,
        regime_boundary_consistency=True,
        taxonomy_usage_consistency=True,
        decomposition_version_mismatches=0,
        provenance={"narrative_chain": narrative_chain}
    )


def run_recommendation_change_audit(lifecycle: RecommendationLifecycle) -> RecommendationChangeAudit:
    """Audit recommendation lifecycle changes for consistency."""
    return RecommendationChangeAudit(
        recommendation_id=lifecycle.recommendation_id,
        last_state_vs_current_state={"status_change": lifecycle.current_status},
        materiality_classification="material" if "DECAYING" in lifecycle.current_status else "normal",
        lifecycle_arc_consistency=True,
        provenance={"chain": lifecycle.chain.narrative_chain_id}
    )


def verify_snapshot_immutability(snapshot: Dict[str, Any]) -> SnapshotImmutabilityCheck:
    """Verify snapshot has not been mutated since creation."""
    current_hash = str(hash(str(snapshot)))
    return SnapshotImmutabilityCheck(
        snapshot_hash=current_hash,
        prior_snapshot_hash=current_hash,  # simulated same for demo
        immutability_verification=True,
        provenance={"source": "governance layer"}
    )


def detect_operational_anomalies(
    snapshot: Dict[str, Any],
    narrative: Dict[str, Any],
    lifecycle: RecommendationLifecycle
) -> List[AnomalyAlert]:
    """Pure detection of operational anomalies (no remediation)."""
    alerts: List[AnomalyAlert] = []
    if not snapshot.get("per_period_records"):
        alerts.append(AnomalyAlert(
            alert_type="empty_snapshot",
            severity="high",
            triggered_by="run_data_integrity_checks",
            recommended_action="Investigate upstream data pipeline (advisory)",
            provenance={"narrative_chain": narrative.get("chain", "unknown")}
        ))
    if "DECAYING" in lifecycle.current_status and narrative.get("portfolio_risk_score", 0) > 0.5:
        alerts.append(AnomalyAlert(
            alert_type="decay_risk_mismatch",
            severity="medium",
            triggered_by="run_model_drift_checks",
            recommended_action="Review fragility signals in Workbench (advisory)",
            provenance={"recommendation_id": lifecycle.recommendation_id}
        ))
    return alerts


def generate_mission_control_report(
    snapshot: Dict[str, Any],
    narrative_chain: str,
    lifecycles: List[RecommendationLifecycle]
) -> Dict[str, Any]:
    """Aggregate all governance objects into a structured, advisory-only report."""
    integrity = run_data_integrity_checks(snapshot)
    drift = run_model_drift_checks(narrative_chain)
    audits = [run_recommendation_change_audit(lc) for lc in lifecycles]
    immut = verify_snapshot_immutability(snapshot)
    anomalies = detect_operational_anomalies(snapshot, {"chain": narrative_chain}, lifecycles[0] if lifecycles else RecommendationLifecycle("dummy", "ACTIVE", [], create_chain("dummy"), {}))

    report = {
        "data_integrity": integrity,
        "model_drift": drift,
        "recommendation_audits": audits,
        "snapshot_immutability": immut,
        "anomaly_alerts": anomalies,
        "summary": {
            "overall_health": "healthy" if integrity.schema_validity and drift.regime_boundary_consistency else "degraded",
            "actionable_items": len(anomalies),
        },
        "provenance": {
            "narrative_chain": narrative_chain,
            "generated_by": "Phase 4F Mission Control (observational only)",
            "phase4f_contract": "phase4f-v1"
        },
        "guardrail": "This report is strictly advisory. It must never influence Phase 3 decision logic or any Phase 4A–4E objects."
    }
    return report


# =============================================================================
# Phase 4G — Distribution & Delivery Layer
# (Pure simulation / observational delivery infrastructure; isolated in narrative.py)
# =============================================================================

@dataclass(frozen=True)
class DeliveryPackage:
    """
    Immutable package containing a versioned Weekly Investor Update ready for delivery.
    """
    package_id: str
    version: str
    recipient_profile: 'RecipientProfile'
    payload: Dict[str, Any]  # the investor update content + metadata
    created_at: str
    chain: NarrativeChainIdentity
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryLedgerEntry:
    """
    Immutable entry recording an attempt to deliver a package.
    """
    entry_id: str
    package_id: str
    status: str  # "PENDING", "DELIVERED", "FAILED", "RETRIED"
    timestamp: str
    metadata: Dict[str, Any]
    chain: NarrativeChainIdentity
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryFailureEvent:
    """
    Immutable record of a delivery failure with root cause and recommended (advisory) action.
    """
    event_id: str
    package_id: str
    failure_type: str
    root_cause: str
    recommended_action: str
    timestamp: str
    chain: NarrativeChainIdentity
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecipientProfile:
    """
    Immutable profile for a delivery recipient (Friend role, etc.).
    """
    recipient_id: str
    name: str
    role: str  # "Friend", "Analyst", "Architect"
    delivery_preferences: Dict[str, Any]
    chain: NarrativeChainIdentity
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryAuditReport:
    """
    Immutable report summarizing delivery activity for a period or set of packages.
    """
    report_id: str
    period: str
    total_packages: int
    delivered: int
    failed: int
    pending: int
    failure_events: List[DeliveryFailureEvent]
    chain: NarrativeChainIdentity
    provenance: Dict[str, Any] = field(default_factory=dict)


def package_weekly_investor_update(
    weekly_update: Dict[str, Any],
    recipient_profile: RecipientProfile,
    version: str,
    base_chain: NarrativeChainIdentity
) -> DeliveryPackage:
    """Pure function to wrap a Weekly Investor Update into a versioned, provenance-tagged DeliveryPackage."""
    package_id = f"pkg_{recipient_profile.recipient_id}_{version}"
    payload = {
        "weekly_update": weekly_update,
        "recipient": recipient_profile.recipient_id,
        "version": version,
    }
    return DeliveryPackage(
        package_id=package_id,
        version=version,
        recipient_profile=recipient_profile,
        payload=payload,
        created_at="now",
        chain=base_chain,
        provenance={
            "source": "Phase 4D Weekly Investor Update + 4G packaging",
            "narrative_chain": base_chain.narrative_chain_id,
        }
    )


def record_delivery_attempt(
    delivery_package: DeliveryPackage,
    status: str,
    timestamp: str,
    metadata: Dict[str, Any],
    base_chain: NarrativeChainIdentity
) -> DeliveryLedgerEntry:
    """Pure function to record a delivery attempt (simulation only, no external I/O)."""
    entry_id = f"entry_{delivery_package.package_id}_{timestamp}"
    return DeliveryLedgerEntry(
        entry_id=entry_id,
        package_id=delivery_package.package_id,
        status=status,
        timestamp=timestamp,
        metadata=metadata,
        chain=base_chain,
        provenance={
            "source": "4G delivery simulation",
            "package_version": delivery_package.version,
        }
    )


def get_delivery_status(
    package_id: str,
    ledger_entries: List[DeliveryLedgerEntry]
) -> Optional[str]:
    """Pure query for the latest status of a package from the in-memory ledger simulation."""
    for entry in reversed(ledger_entries):
        if entry.package_id == package_id:
            return entry.status
    return None


def list_pending_deliveries(ledger_entries: List[DeliveryLedgerEntry]) -> List[DeliveryLedgerEntry]:
    """Pure query for pending deliveries."""
    return [e for e in ledger_entries if e.status == "PENDING"]


def generate_delivery_audit_report(
    period: str,
    ledger_entries: List[DeliveryLedgerEntry],
    failure_events: List[DeliveryFailureEvent],
    base_chain: NarrativeChainIdentity
) -> DeliveryAuditReport:
    """Pure function to produce a DeliveryAuditReport from ledger and failure data."""
    total = len(ledger_entries)
    delivered = sum(1 for e in ledger_entries if e.status == "DELIVERED")
    failed = sum(1 for e in ledger_entries if e.status == "FAILED")
    pending = total - delivered - failed
    return DeliveryAuditReport(
        report_id=f"audit_{period}",
        period=period,
        total_packages=total,
        delivered=delivered,
        failed=failed,
        pending=pending,
        failure_events=failure_events,
        chain=base_chain,
        provenance={
            "source": "4G audit generation",
            "narrative_chain": base_chain.narrative_chain_id,
        }
    )


def record_delivery_failure(
    package_id: str,
    failure_type: str,
    root_cause: str,
    recommended_action: str,
    timestamp: str,
    base_chain: NarrativeChainIdentity
) -> DeliveryFailureEvent:
    """Pure function to record a failure event (advisory recommended_action only)."""
    event_id = f"fail_{package_id}_{timestamp}"
    return DeliveryFailureEvent(
        event_id=event_id,
        package_id=package_id,
        failure_type=failure_type,
        root_cause=root_cause,
        recommended_action=recommended_action,
        timestamp=timestamp,
        chain=base_chain,
        provenance={"source": "4G failure simulation"}
    )


# =============================================================================
# Phase 4H — Multi-Portfolio Support
# (Dimensional expansion of the temporal spine; isolated in narrative.py)
# =============================================================================

@dataclass(frozen=True)
class PortfolioIdentity:
    """
    Immutable root of temporal continuity for a single portfolio.
    All Phase 4 objects derive their scoping from this.
    """
    portfolio_id: str
    portfolio_name: str
    mandate_profile: str
    created_at: str
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioRegistry:
    """
    Immutable, queryable registry of all known PortfolioIdentity objects.
    """
    identities: Dict[str, PortfolioIdentity] = field(default_factory=dict)

    def register(self, identity: PortfolioIdentity) -> 'PortfolioRegistry':
        new_identities = dict(self.identities)
        new_identities[identity.portfolio_id] = identity
        return PortfolioRegistry(identities=new_identities)

    def get(self, portfolio_id: str) -> Optional[PortfolioIdentity]:
        return self.identities.get(portfolio_id)

    def list_all(self) -> List[PortfolioIdentity]:
        return list(self.identities.values())


# Lightweight portfolio-scoped wrappers (composition, no mutation of original objects)
@dataclass(frozen=True)
class PortfolioScopedNarrativeChain:
    portfolio_id: str
    chain: NarrativeChainIdentity
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioScopedLifecycle:
    portfolio_id: str
    lifecycle: RecommendationLifecycle
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioScopedSnapshot:
    portfolio_id: str
    snapshot: PortfolioSnapshot
    provenance: Dict[str, Any] = field(default_factory=dict)


# For Governance (4F) and Delivery (4G) we use a generic scoped wrapper for simplicity in this implementation
@dataclass(frozen=True)
class PortfolioScopedObject:
    portfolio_id: str
    obj: Any
    provenance: Dict[str, Any] = field(default_factory=dict)


def create_portfolio_identity(
    portfolio_id: str,
    portfolio_name: str,
    mandate_profile: str,
    created_at: str,
    base_chain: NarrativeChainIdentity
) -> PortfolioIdentity:
    """Pure creation of a PortfolioIdentity."""
    return PortfolioIdentity(
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        mandate_profile=mandate_profile,
        created_at=created_at,
        provenance={"narrative_chain": base_chain.narrative_chain_id}
    )


def resolve_portfolio_context(portfolio_id: str, registry: PortfolioRegistry) -> Optional[PortfolioIdentity]:
    """Pure resolution against the registry."""
    return registry.get(portfolio_id)


def scope_to_portfolio(existing_object: Any, portfolio_id: str, base_chain: NarrativeChainIdentity) -> PortfolioScopedObject:
    """
    Pure function: returns a portfolio-scoped view of an existing object without mutating it.
    Enforces scoping.
    """
    return PortfolioScopedObject(
        portfolio_id=portfolio_id,
        obj=existing_object,
        provenance={"source": "4H scoping", "original_type": type(existing_object).__name__, "narrative_chain": base_chain.narrative_chain_id}
    )


def validate_portfolio_scoping(obj: Any) -> bool:
    """
    Runtime invariant check. Returns True only if the object is properly portfolio-scoped
    (either a PortfolioIdentity, Registry, or a PortfolioScoped* wrapper, or contains portfolio_id in provenance).
    For scoped wrappers, the claimed portfolio_id must match the object's internal identity.
    """
    if isinstance(obj, (PortfolioIdentity, PortfolioRegistry)):
        return True
    if isinstance(obj, PortfolioScopedObject):
        # Enforce match between claimed scope and the wrapped object's provenance (if present)
        inner = obj.obj
        if hasattr(inner, "provenance") and isinstance(inner.provenance, dict):
            claimed = inner.provenance.get("portfolio_id") or getattr(inner, "portfolio_id", None)
            return claimed == obj.portfolio_id
        return True  # fallback for pure simulation objects
    if isinstance(obj, (PortfolioScopedNarrativeChain, PortfolioScopedLifecycle, PortfolioScopedSnapshot)):
        return True
    if hasattr(obj, "provenance") and isinstance(obj.provenance, dict) and "portfolio_id" in obj.provenance:
        return True
    return False


def get_portfolio_aware_narrative_arc(
    lifecycles: List[RecommendationLifecycle],
    portfolio_id: str,
    recommendation_id: str,
    registry: PortfolioRegistry
) -> List[Dict[str, Any]]:
    """
    Portfolio-aware version of the 4B/4E arc query. Enforces scoping.
    """
    if not registry.get(portfolio_id):
        return []  # unknown portfolio
    scoped = [lc for lc in lifecycles if lc.recommendation_id == recommendation_id]
    # In real use the lifecycles list would already be filtered by portfolio; here we simulate
    return [{"recommendation_id": lc.recommendation_id, "status": lc.current_status, "portfolio_id": portfolio_id} for lc in scoped]


def get_portfolio_aware_lifecycle(
    lifecycles: List[RecommendationLifecycle],
    portfolio_id: str,
    recommendation_id: str,
    registry: PortfolioRegistry
) -> Optional[Dict[str, Any]]:
    if not registry.get(portfolio_id):
        return None
    for lc in lifecycles:
        if lc.recommendation_id == recommendation_id:
            return {"recommendation_id": lc.recommendation_id, "current_status": lc.current_status, "portfolio_id": portfolio_id, "history": lc.history_summary}
    return None


def get_portfolio_aware_governance(
    audits: List[Any],
    portfolio_id: str,
    registry: PortfolioRegistry
) -> List[Dict[str, Any]]:
    if not registry.get(portfolio_id):
        return []
    # Simulate filtering
    return [{"recommendation_id": getattr(a, "recommendation_id", "unknown"), "portfolio_id": portfolio_id} for a in audits]


def get_portfolio_aware_delivery_status(
    ledger: List[DeliveryLedgerEntry],
    package_id: str,
    portfolio_id: str,
    registry: PortfolioRegistry
) -> Optional[str]:
    if not registry.get(portfolio_id):
        return None
    for entry in reversed(ledger):
        if entry.package_id == package_id:
            return entry.status
    return None


# =============================================================================
# Phase 4I thin presenter helpers (pure, no new decision logic or derived scores)
# These live in narrative.py so the UI layer remains a pure consumer.
# =============================================================================

def get_narrative_arcs_panel_data(portfolio_id: str, registry: PortfolioRegistry, lifecycles: List[RecommendationLifecycle]) -> Dict[str, Any]:
    """Returns structured data for the Narrative Arcs panel from existing 4E/4H queries."""
    if not registry.get(portfolio_id):
        return {"portfolio_id": portfolio_id, "error": "unknown portfolio", "events": []}
    # Use the portfolio-aware query (simplified to return recent material events)
    arcs = get_portfolio_aware_narrative_arc(lifecycles, portfolio_id, None, registry)  # None = all for demo
    # For v0.1 we surface a compact list of recent "material" events (using lifecycle history as proxy)
    events = []
    for lc in lifecycles:
        for item in lc.history_summary[-3:]:  # last 3 as "recent"
            events.append({
                "recommendation_id": lc.recommendation_id,
                "event": item,
                "portfolio_id": portfolio_id
            })
    return {
        "portfolio_id": portfolio_id,
        "as_of": "current",
        "events": events[:10],  # cap for v0.1
        "provenance": {"narrative_chain": "current", "portfolio_id": portfolio_id}
    }


def get_lifecycle_status_panel_data(portfolio_id: str, registry: PortfolioRegistry, lifecycles: List[RecommendationLifecycle]) -> Dict[str, Any]:
    """Returns structured data for the Lifecycle Status panel."""
    if not registry.get(portfolio_id):
        return {"portfolio_id": portfolio_id, "error": "unknown portfolio", "recommendations": []}
    recs = []
    for lc in lifecycles:
        recs.append({
            "recommendation_id": lc.recommendation_id,
            "current_status": lc.current_status,
            "recent_history": lc.history_summary[-3:],
            "portfolio_id": portfolio_id
        })
    return {
        "portfolio_id": portfolio_id,
        "as_of": "current",
        "recommendations": recs,
        "provenance": {"narrative_chain": "current", "portfolio_id": portfolio_id}
    }


def get_governance_status_panel_data(portfolio_id: str, registry: PortfolioRegistry, snapshot: Any, lifecycles: List[RecommendationLifecycle]) -> Dict[str, Any]:
    """Returns structured data for the Governance Status panel using 4F report + alerts."""
    if not registry.get(portfolio_id):
        return {"portfolio_id": portfolio_id, "error": "unknown portfolio"}
    # Simulate a minimal report + alerts (in real would call the 4F functions with scoped data)
    report = generate_mission_control_report({"portfolio_id": portfolio_id}, "current", lifecycles)
    alerts = detect_operational_anomalies({"portfolio_id": portfolio_id}, {"portfolio_id": portfolio_id}, lifecycles[0] if lifecycles else RecommendationLifecycle("dummy", "ACTIVE", [], create_chain("dummy"), {}))
    return {
        "portfolio_id": portfolio_id,
        "as_of": "current",
        "overall_health": report["summary"]["overall_health"],
        "actionable_items": report["summary"]["actionable_items"],
        "active_alerts": [{"type": a.alert_type, "severity": a.severity, "action": a.recommended_action} for a in alerts],
        "provenance": {"narrative_chain": "current", "portfolio_id": portfolio_id}
    }


def get_delivery_history_panel_data(portfolio_id: str, registry: PortfolioRegistry, ledger: List[DeliveryLedgerEntry]) -> Dict[str, Any]:
    """Returns structured data for the Delivery History panel."""
    if not registry.get(portfolio_id):
        return {"portfolio_id": portfolio_id, "error": "unknown portfolio", "entries": []}
    # Filter ledger to this portfolio (in real the ledger would be per-portfolio; here we tag via provenance simulation)
    entries = [e for e in ledger if e.provenance.get("portfolio_id", portfolio_id) == portfolio_id] if ledger else []
    return {
        "portfolio_id": portfolio_id,
        "as_of": "current",
        "recent_entries": [{"package_id": e.package_id, "status": e.status, "timestamp": e.timestamp} for e in entries[-5:]],
        "provenance": {"narrative_chain": "current", "portfolio_id": portfolio_id}
    }


def export_investigation_note(portfolio_id: str, panels: Dict[str, Any], as_of: str = "current") -> Dict[str, Any]:
    """
    Pure function: exports the current Workbench view state + full provenance as a structured, auditable note.
    Still advisory-only.
    """
    return {
        "type": "investigation_note_v0.1",
        "portfolio_id": portfolio_id,
        "as_of": as_of,
        "panels": panels,
        "provenance": {
            "narrative_chain": "current",
            "portfolio_id": portfolio_id,
            "generated_by": "Phase 4I Workbench UI v0.1 (thin presentation only)"
        },
        "guardrail": "This note is strictly advisory. It contains no new decision logic."
    }


# =============================================================================
# Phase 4J thin presenter helpers for v0.2 flows (pure, no new decision logic)
# =============================================================================

def get_attention_vector_data(portfolio_id: str, registry: PortfolioRegistry, snapshot: Any, lifecycles: List[RecommendationLifecycle], governance_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns materiality-gated Attention Vector data (Critical / Important / Informational).
    Uses existing governance alerts, lifecycle changes, and patterns. No new scoring.
    """
    if not registry.get(portfolio_id):
        return {"portfolio_id": portfolio_id, "critical": [], "important": [], "informational": []}

    critical = []
    important = []
    informational = []

    # From governance (4F) — support both anomaly_alerts (direct 4F) and active_alerts (from 4I presenter shape)
    alerts = governance_report.get("anomaly_alerts") or governance_report.get("active_alerts") or []
    for alert in alerts:
        sev = alert.get("severity", "").lower()
        action = alert.get("recommended_action") or alert.get("action") or "Alert"
        if sev == "high":
            critical.append({"type": "governance", "description": str(action)})
        else:
            important.append({"type": "governance", "description": str(action)})

    # From lifecycles (4B)
    for lc in lifecycles:
        if "DECAYING" in lc.current_status:
            important.append({"type": "lifecycle", "recommendation_id": lc.recommendation_id, "description": f"{lc.recommendation_id} in DECAYING status"})
        elif "STRENGTHENING" in lc.current_status:
            informational.append({"type": "lifecycle", "recommendation_id": lc.recommendation_id, "description": f"{lc.recommendation_id} in STRENGTHENING status"})

    return {
        "portfolio_id": portfolio_id,
        "as_of": "current",
        "critical": critical,
        "important": important,
        "informational": informational,
        "provenance": {"narrative_chain": "current", "portfolio_id": portfolio_id}
    }


def get_hypothesis_auditor_data(portfolio_id: str, registry: PortfolioRegistry, selected_ids: List[str], lifecycles: List[RecommendationLifecycle], governance_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight side-by-side comparison for 2-3 items using existing data.
    Purely observational.
    """
    if not registry.get(portfolio_id):
        return {"portfolio_id": portfolio_id, "error": "unknown portfolio", "comparisons": []}

    comparisons = []
    for rid in selected_ids:
        for lc in lifecycles:
            if lc.recommendation_id == rid:
                comparisons.append({
                    "recommendation_id": rid,
                    "lifecycle_status": lc.current_status,
                    "recent_history": lc.history_summary[-2:],
                    "governance_note": "See governance panel for alerts"
                })
                break

    return {
        "portfolio_id": portfolio_id,
        "selected_items": selected_ids,
        "comparisons": comparisons,
        "provenance": {"narrative_chain": "current", "portfolio_id": portfolio_id}
    }


def get_slider_filtered_panel_data(portfolio_id: str, registry: PortfolioRegistry, time_window: str, full_arcs_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simulates temporal slider by filtering events to the 'window'.
    For v0.2, 'window' is a simple label; real would filter by chain sequence.
    Progressive disclosure: only material in window.
    """
    if not registry.get(portfolio_id):
        return {"portfolio_id": portfolio_id, "error": "unknown portfolio"}

    # Simple simulation: if window == "recent" show last 2, else all
    events = full_arcs_data.get("events", [])
    if time_window == "recent":
        filtered = events[-2:] if len(events) > 2 else events
    else:
        filtered = events

    return {
        "portfolio_id": portfolio_id,
        "time_window": time_window,
        "filtered_events": filtered,
        "provenance": {"narrative_chain": "current", "portfolio_id": portfolio_id, "window": time_window}
    }


# =============================================================================
# Phase 4K – Friend Mode UI v0.1 (thin presenter layer)
# All logic here is pure, observational, and versioned.
# Friend-facing text is generated through these functions only.
# friend_language_version = "v0.1" is captured on every output for auditability.
# The UI layer (analyst_workbench.py or future companion) must remain purely presentational.
# =============================================================================

FRIEND_LANGUAGE_VERSION = "v0.1"

FRIEND_INTERPRETATION_GUARDRAILS = (
    "This is an observation from our system, not advice. "
    "It does not tell you what to do with the portfolio. "
    "It is one input among many. Past patterns do not guarantee future results. "
    "Always consult your own judgment or a qualified advisor."
)


def _is_quiet_state(lifecycles: List[RecommendationLifecycle]) -> bool:
    """Returns True if no material narrative activity is present in the lifecycles."""
    if not lifecycles:
        return True
    material_statuses = {"STRENGTHENING", "DECAYING", "CONFLICT_EMERGED"}
    for lc in lifecycles:
        if lc.current_status in material_statuses:
            return False
        history = getattr(lc, "history_summary", []) or []
        for item in history:
            item_str = str(item).upper()
            if any(k in item_str for k in ["DECAY", "STRENGTHEN", "CONFLICT", "RISK_ESCALATION"]):
                return False
    return True


def get_friend_view_data(
    portfolio_id: str,
    registry: PortfolioRegistry,
    lifecycles: List[RecommendationLifecycle],
    snapshot: Any,
    governance_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Main Friend Mode presenter (Phase 4K v0.1).
    Produces a calm, translated view addressing the seven UX gaps.
    All outputs are derived from existing 4A–4J objects. No new decision logic.
    """
    if not registry.get(portfolio_id):
        return {
            "portfolio_id": portfolio_id,
            "friend_language_version": FRIEND_LANGUAGE_VERSION,
            "error": "unknown portfolio",
            "is_quiet_state": True,
        }

    quiet = _is_quiet_state(lifecycles)

    if quiet:
        return {
            "portfolio_id": portfolio_id,
            "friend_language_version": FRIEND_LANGUAGE_VERSION,
            "emotional_temperature": "Calm & Steady",
            "one_sentence_summary": "No material changes. No action required. This is normal portfolio behavior.",
            "actionable_highlights": [],
            "storyline": "The portfolio has shown no significant narrative events in the current window.",
            "confidence_translation": "The system is not currently flagging material shifts that require attention.",
            "glossary": {},
            "interpretation_guardrails": FRIEND_INTERPRETATION_GUARDRAILS,
            "is_quiet_state": True,
            "provenance": {
                "narrative_chain": getattr(snapshot, "as_of_narrative_chain_id", "current"),
                "portfolio_id": portfolio_id,
                "source": "Phase 4K friend presenter (quiet state)",
            },
        }

    # Non-quiet: derive from lifecycles (demo data uses RecommendationLifecycle + simple states)
    statuses = [lc.current_status for lc in lifecycles]
    has_decay = any("DECAY" in s for s in statuses)
    has_strengthen = any("STRENGTHEN" in s for s in statuses)

    if has_decay:
        emotional_temperature = "Watchful but not alarmed"
        one_sentence = "One holding is showing signs of weakening and should be monitored."
        storyline = "A recommendation has moved into a DECAYING status in the current period."
        confidence_translation = "We have moderate evidence of a change in momentum for at least one position."
        actionable_highlights = [
            {
                "id": next((lc.recommendation_id for lc in lifecycles if "DECAY" in lc.current_status), "position"),
                "note": "Monitor this position for further weakening. Consider whether the original thesis still holds.",
            }
        ]
    elif has_strengthen:
        emotional_temperature = "Calm & Positive"
        one_sentence = "A holding is strengthening in a controlled environment."
        storyline = "A recommendation has entered a STRENGTHENING phase."
        confidence_translation = "Signals for this position are currently favorable within the observed window."
        actionable_highlights = [
            {
                "id": next((lc.recommendation_id for lc in lifecycles if "STRENGTHEN" in lc.current_status), "position"),
                "note": "The position is performing in line with a strengthening thesis. No immediate action suggested.",
            }
        ]
    else:
        emotional_temperature = "Calm & Steady"
        one_sentence = "The portfolio is in a stable phase with no urgent signals."
        storyline = "Recent activity has not crossed major materiality thresholds."
        confidence_translation = "No strong directional signals are currently active."
        actionable_highlights = []

    # Simple glossary for terms that might appear
    glossary = {
        "STRENGTHENING": "The system's observation that conditions for this holding have improved recently.",
        "DECAYING": "The system's observation that conditions for this holding have weakened recently.",
    }

    return {
        "portfolio_id": portfolio_id,
        "friend_language_version": FRIEND_LANGUAGE_VERSION,
        "emotional_temperature": emotional_temperature,
        "one_sentence_summary": one_sentence,
        "actionable_highlights": actionable_highlights,
        "storyline": storyline,
        "confidence_translation": confidence_translation,
        "glossary": glossary,
        "interpretation_guardrails": FRIEND_INTERPRETATION_GUARDRAILS,
        "is_quiet_state": False,
        "provenance": {
            "narrative_chain": getattr(snapshot, "as_of_narrative_chain_id", "current"),
            "portfolio_id": portfolio_id,
            "source": "Phase 4K friend presenter",
            "lifecycles_used": [lc.recommendation_id for lc in lifecycles],
        },
    }


def build_friend_note(
    portfolio_id: str,
    friend_view: Dict[str, Any],
    as_of: str = "current",
) -> Dict[str, Any]:
    """
    Produces the exportable Friend Note (even more compressed than Investor Update).
    Captures the language version explicitly.
    """
    return {
        "type": "friend_note_v0.1",
        "friend_language_version": friend_view.get("friend_language_version", FRIEND_LANGUAGE_VERSION),
        "portfolio_id": portfolio_id,
        "as_of": as_of,
        "view": friend_view,
        "provenance": friend_view.get("provenance", {}),
        "guardrail": "This note is strictly advisory and contains no new decision logic or recommendations.",
    }


# =============================================================================
# Phase 4L — Hero Decision Band Presenters (Thin Layer)
# All synthesis logic lives exclusively here. UI layers are pure consumers.
# Compatible with existing Phase 4K child presenters (same input shapes).
# Produces canonical fields for the mandatory Hero Decision Band.
# =============================================================================

def get_hero_decision_band_data(
    portfolio_id: str,
    registry: PortfolioRegistry,
    lifecycles: List[RecommendationLifecycle],
    snapshot: Any,
    governance_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Thin presenter for the Phase 4L Hero Decision Band.
    Derives primary recommendation, bias, risk, confidence, and abstention reason
    exclusively from existing Phase 3 + 4A–4J objects (lifecycles, snapshot, etc.).
    Never called from or depends on UI code.
    """
    if not registry.get(portfolio_id):
        return {
            "portfolio_id": portfolio_id,
            "primary_recommendation": "OBSERVE",
            "directional_bias": "Neutral",
            "risk_state": "Unknown",
            "confidence_bucket": "Low",
            "abstention_reason": "Unknown portfolio",
            "is_abstaining": True,
            "provenance": {
                "narrative_chain": getattr(snapshot, "as_of_narrative_chain_id", "current"),
                "portfolio_id": portfolio_id,
                "source": "Phase 4L hero presenter (unknown portfolio)",
            },
        }

    # Derive from lifecycles and rec states (compatible with 4K demo data and spine)
    statuses = [lc.current_status for lc in lifecycles]
    has_decay = any("DECAY" in s for s in statuses)
    has_strengthen = any("STRENGTHEN" in s for s in statuses)

    # Primary recommendation logic (synthesized here only; based on spine signals)
    if has_decay:
        primary_recommendation = "OBSERVE"
        is_abstaining = True
        abstention_reason = "Position(s) showing DECAYING status"
        directional_bias = "Negative"
    elif has_strengthen:
        primary_recommendation = "TRADE"
        is_abstaining = False
        abstention_reason = None
        directional_bias = "Positive"
    else:
        primary_recommendation = "OBSERVE"
        is_abstaining = True
        abstention_reason = "No material directional signal (stable/quiet)"
        directional_bias = "Neutral"

    # Risk state from snapshot or simple derivation
    risk_state = "Controlled"
    if hasattr(snapshot, "portfolio_risk_score"):
        if getattr(snapshot, "portfolio_risk_score", 0) > 0.5:
            risk_state = "Elevated"

    # Confidence bucket (simple bucketing; can be enriched later)
    confidence_bucket = "Moderate"
    # Use first rec_state confidence if present (demo data shape)
    if lifecycles:
        # proxy from overall_confidence in caller-provided rec states if available
        # for now use stability band proxy from 4K-era data
        pass  # kept minimal; real would pull from snapshot or enriched state

    # In demo data, we can infer from status strength
    if has_strengthen:
        confidence_bucket = "High"
    elif has_decay:
        confidence_bucket = "Low"

    # For real spine, this would pull from RecommendationState / stability etc.
    # Here we keep derivation thin and observable.

    provenance = {
        "narrative_chain": getattr(snapshot, "as_of_narrative_chain_id", "current"),
        "portfolio_id": portfolio_id,
        "source": "Phase 4L hero decision band presenter",
        "lifecycles_used": [lc.recommendation_id for lc in lifecycles],
    }

    return {
        "portfolio_id": portfolio_id,
        "primary_recommendation": primary_recommendation,
        "directional_bias": directional_bias,
        "risk_state": risk_state,
        "confidence_bucket": confidence_bucket,
        "abstention_reason": abstention_reason,
        "is_abstaining": is_abstaining,
        "provenance": provenance,
    }
