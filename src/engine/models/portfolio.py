"""
Portfolio Layer core data models (Phase 1 – Chunk A).

These dataclasses materialize the locked Phase 0 contracts:
- Chunk 3: Minimal PortfolioStateSnapshot Schema v1.0
- Phase 0 Addendum – Pre-Phase 1 Clarifications (v1.0)

Scope for Phase 1 Chunk A is strictly limited to the data models themselves.
No persistence, no seeding logic, no intelligence layers, and no recommendation engines.

All Explanation Engine fields are treated as first-class citizens in the schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class HoldingSnapshot:
    """
    Per-holding state within a PortfolioStateSnapshot.

    Mirrors the locked Chunk 3 schema exactly, with the bucket_id
    clarification from the Phase 0 Addendum review.
    """
    # Identity & acquisition (ground truth)
    ticker: str
    acquisition_date: date
    acquisition_price: float
    shares_initial: float
    initial_investment_value: float
    initial_weight_pct: float

    # Current state (as-of snapshot date)
    shares_current: float
    current_price: float
    current_value: float
    pnl_abs: float
    pnl_pct: float
    current_weight_pct: float

    # Cost basis (required for tax-aware logic in later phases)
    tax_basis: float

    bucket_id: Optional[str] = None  # Optional support for bucketing (core vs. tactical, preservation vs. growth, etc.)

    # Signals from the engine / Action Ontology (advisory only)
    rocket_state: Optional[str] = None
    rocket_trend_5d: Optional[str] = None
    transitional_state: Optional[str] = None
    rs_acceleration: Optional[float] = None
    adaptive_risk_decay_state: Optional[str] = None
    tactical_bias: Optional[str] = None

    expected_return_12w: Optional[float] = None
    expected_return_12m: Optional[float] = None
    expected_return_trend_12w: Optional[str] = None

    dividend_mode: Optional[str] = None  # "REINVEST" or "HARVEST"

    # Action selected from the Action Ontology
    action: Optional[str] = None

    # Explanation Engine fields (first-class citizens)
    action_rationale: Optional[Dict[str, Any]] = None
    # Structured explanation for this holding's action/suppression.
    # Must contain at minimum:
    #   - primary_reason
    #   - contributing_signals
    #   - applied_filters
    #   - plain_language_statement
    # (exact keys will be enforced by later Explanation Engine contracts)


@dataclass
class PortfolioStateSnapshot:
    """
    Core point-in-time record for a portfolio (v1.0 minimal contract + Phase 2 extensions).

    This class is the direct implementation of the locked Chunk 3 schema
    plus the four clarifications from the Phase 0 Addendum, and Phase 2
    intelligence fields for persistable integration (Chunk B) plus provenance
    (Chunk C).

    Phase 1 rules:
    - intelligence_layers_enabled must remain False.
    - mutation_rules must default to read-only behavior.
    - data_completeness starts at "manual_seed".
    """

    # --- Top-level metadata ---
    # All non-default (required) fields must come before any fields with defaults.
    portfolio_id: str
    portfolio_name: str
    portfolio_type: str  # One of the 12 locked portfolio types
    as_of_date: date
    source: str  # e.g. "manual_seed", "nightly_update"

    # --- Portfolio-level fields ---
    total_value: float
    total_pnl_abs: float
    total_pnl_pct: float

    # Fields with defaults (must come after all required fields)
    snapshot_version: str = "1.0"
    generated_at: datetime = field(default_factory=datetime.utcnow)
    cash_unallocated_pct: float = 0.0

    expected_return_12w: Optional[float] = None
    expected_return_12m: Optional[float] = None
    expected_return_trend_12w: Optional[str] = None

    risk_regime: Optional[str] = None
    transitional_state: Optional[str] = None
    action_urgency: Optional[str] = None
    # Allowed values: "Low", "Watch", "Elevated", "High", "Critical"

    rebalance_recommendation_12w: Optional[str] = None
    rebalance_rationale: Optional[str] = None

    # --- Phase 0 Addendum clarifications ---
    mutation_rules: Dict[str, Any] = field(default_factory=dict)
    # Phase 1: must default to read-only behavior.
    # No actual mutations are permitted until later phases explicitly enable them.

    intelligence_layers_enabled: bool = False
    # Phase 1: must remain False.
    # All intelligence layers (scoring, expectations, rebalancing logic, etc.) are disabled.
    # This flag provides a clear contractual switch for future phases.

    data_completeness: str = "manual_seed"
    # Initial allowed value: "manual_seed"
    # Future values will expand to include "live_update", "validated", "backfilled", etc.

    # --- Placeholders for future expansion (post Phase 1) ---
    mandate_drift_index: Optional[float] = None
    allocation_pressure: Optional[Dict[str, Any]] = None

    # --- Phase 2 intelligence fields (added in Chunk B for persistable integration) ---
    tactical_action: Optional[str] = None
    signal_stability_score: Optional[float] = None
    basic_rebalance_recommendation: Optional[str] = None

    # --- Phase 2 provenance (added in Chunk C) ---
    intelligence_provenance: Optional[Dict[str, Any]] = None

    # --- Holdings ---
    holdings: List[HoldingSnapshot] = field(default_factory=list)

    # --- Basic context placeholders (lightweight) ---
    news_context: Optional[Dict[str, Any]] = None
    corporate_action_context: Optional[Dict[str, Any]] = None
    outlier_events: List[Dict[str, Any]] = field(default_factory=list)

    # --- Explanation Engine fields (first-class citizens) ---
    logic_trace: List[Dict[str, Any]] = field(default_factory=list)
    # Ordered list of rules, filters, and decisions applied when building this snapshot.
    # Each entry should be a small dict with at least "rule" and "result".

    action_rationale: Optional[Dict[str, Any]] = None
    # Portfolio-level summary rationale. Must be suitable for a Logic Dashboard.

    unified_portfolio_view_rationale: Optional[str] = None
    # Human-consumable text that reconciles signals across holdings/buckets
    # into one coherent narrative the user (or their spouse/advisor) can understand
    # without needing to reconcile conflicting signals themselves.

    escalation_notifications: List[Dict[str, Any]] = field(default_factory=list)
    # Any MANUAL_REVIEW_ESCALATION or similar events that occurred.
    # Each entry should include "type", "trigger", "message", and "timestamp".
