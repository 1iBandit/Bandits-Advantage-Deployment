"""
Friend Profile — Personalization layer for the active Friend Mode guide.

This module is strictly isolated from Phase 3 decision logic.
FriendProfile is user/advisor-level context that powers behavioral guidance,
question sequencing, and adaptive communication — without ever mutating
PortfolioSnapshot, RecommendationLifecycle, or any decision outputs.

All objects are immutable (frozen dataclass).

See the Phase 4K / active guide evolution for usage patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass(frozen=True)
class FriendProfile:
    """
    Canonical, immutable profile that turns the Friend from passive translator
    into an active behavioral guide and "next question" architect.

    Design principles:
    - Minimal but high-signal fields that enable real personalization.
    - Immutable for safety and provenance hygiene (consistent with Phase 4A+).
    - Explicit versioning so the profile can evolve without breaking consumers.
    - Does NOT attach to or mutate PortfolioSnapshot / core decision objects.
    - Can be passed optionally into presenters (get_friend_view_data, etc.).
    """

    profile_id: str
    version: int = 1

    # Core identity
    personality_type: str = "BalancedCore"
    # Examples (canonical set will be locked later):
    # "GrowthSeeker", "CapitalPreserver", "IncomeOptimizer",
    # "ContrarianOpportunist", "BalancedCore"

    # Goals & Constraints (high-leverage for question leading)
    primary_goals: List[str] = field(default_factory=list)
    # e.g. ["long_term_capital_growth", "current_income", "capital_preservation",
    #       "legacy_transfer", "inflation_protection"]

    risk_constraints: Dict[str, Any] = field(default_factory=dict)
    # e.g. {"max_drawdown_pct": 12.0, "max_portfolio_volatility": 0.16,
    #       "min_liquidity_pct": 20.0, "avoid_leverage": True}

    # Allocation boundaries (prevents bad recommendations from feeling personal)
    sector_caps: Dict[str, float] = field(default_factory=dict)
    # e.g. {"Technology": 0.30, "Energy": 0.15}

    ticker_caps: Dict[str, float] = field(default_factory=dict)
    # e.g. {"NVDA": 0.07, "TSLA": 0.05}

    # Behavioral intelligence (the "blind spots" the guide must remember)
    behavioral_tendencies: List[str] = field(default_factory=list)
    # e.g. ["recency_bias", "loss_aversion", "overconfidence", "herding",
    #       "anchoring_on_purchase_price", "neglect_of_base_rates"]

    historical_patterns: Dict[str, Any] = field(default_factory=dict)
    # Lightweight observed history (not full replay data):
    # e.g. {"times_sold_at_bottom": 2, "chased_momentum_last_3y": True,
    #       "average_hold_period_months": 14}

    # How the guide should communicate and lead
    communication_preference: str = "balanced"
    # "concise", "detailed", "question_driven", "story_driven", "balanced"

    # Open space for user overrides or advisor notes
    free_text_notes: str = ""

    # Audit / evolution fields (consistent with existing provenance patterns)
    created_at: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Safe serialization (no mutation of internals)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FriendProfile":
        """Reconstruct from dict. Unknown keys are ignored for forward compatibility."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# Convenience factory for a sensible starter profile (used in demos / tests)
def create_example_friend_profile(
    profile_id: str = "demo_user_001",
    personality_type: str = "BalancedCore",
    **overrides: Any,
) -> FriendProfile:
    base = {
        "primary_goals": ["long_term_capital_growth", "moderate_income"],
        "risk_constraints": {"max_drawdown_pct": 15.0},
        "sector_caps": {"Technology": 0.35},
        "ticker_caps": {"NVDA": 0.08},
        "behavioral_tendencies": ["recency_bias", "loss_aversion"],
        "communication_preference": "balanced",
        "created_at": "2026-06-13",
        "provenance": {"source": "initial_onboarding", "version": 1},
    }
    base.update(overrides)
    return FriendProfile(
        profile_id=profile_id,
        version=1,
        personality_type=personality_type,
        **base,
    )


def apply_profile_edits(
    current: FriendProfile, edits: Dict[str, Any]
) -> FriendProfile:
    """
    Pure helper: takes an existing profile and a dict of changes,
    returns a new immutable profile with incremented version.
    Used by thin UI layers for editable profile surfaces.
    """
    data = current.to_dict()
    data.update(edits)
    data["version"] = current.version + 1
    prov = dict(data.get("provenance", {}))
    prov["last_edited_at"] = "session"
    data["provenance"] = prov
    return FriendProfile.from_dict(data)
