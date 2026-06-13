"""
Portfolio Layer package (Phase 1+).

Currently contains:
- persistence: JSONL append-only storage for PortfolioStateSnapshot
"""

from .persistence import (
    save_snapshot,
    load_latest_snapshot,
    load_snapshot_history,
    load_latest_snapshot_v2,
)
from .seeding import (
    load_portfolio_definitions,
    seed_from_csv,
    create_example_capital_preservation_seed,
)
from .intelligence import (
    aggregate_portfolio_signals,
    map_to_tactical_action,
    compute_basic_rebalance_recommendation,
    compute_early_signal_stability,
    enrich_snapshot_with_basic_intelligence,
    apply_basic_intelligence_to_snapshot,
    create_enriched_snapshot,
    analyze_stability_on_replay,
    run_simulator_shadow,
    apply_decision_layer_rules,
    run_simulator_shadow_multi,
    slice_rows_by_date,
    generate_rolling_windows,
    build_multi_summary,
    compute_rule_set_deltas,
    extract_stability_band_insights,
    extract_regime_insights,
    extract_portfolio_type_insights,
    build_calibration_summary,
    build_consolidated_calibration_report,
    rank_top_opportunities,
    rank_top_risks,
    identify_rule_refinement_targets,
    identify_low_value_refinement_areas,
    compute_signal_strength_score,
    compute_stability_sensitivity_score,
    compute_regime_sensitivity_score,
    compute_portfolio_type_impact_score,
    evaluate_rule_set_impact,
    analyze_rule_set_impact,
    generate_calibration_recommendations,
    describe_calibration_export_contract,
    export_for_daily_delta_tracker,
    export_for_logic_dashboard,
)

# Phase 4K Friend Mode thin presenters (re-exported for convenience; all logic remains in narrative.py)
from .narrative import (
    get_friend_view_data,
    build_friend_note,
    FRIEND_LANGUAGE_VERSION,
)

# Phase 4L — Decision Surface (Hero Decision Band)
# Thin presenters only — all synthesis logic remains in narrative.py
from .narrative import (
    get_hero_decision_band_data,
)

__all__ = [
    "save_snapshot",
    "load_latest_snapshot",
    "load_snapshot_history",
    "load_latest_snapshot_v2",
    "load_portfolio_definitions",
    "seed_from_csv",
    "create_example_capital_preservation_seed",
    "aggregate_portfolio_signals",
    "map_to_tactical_action",
    "compute_basic_rebalance_recommendation",
    "compute_early_signal_stability",
    "enrich_snapshot_with_basic_intelligence",
    "apply_basic_intelligence_to_snapshot",
    "create_enriched_snapshot",
    "analyze_stability_on_replay",
    "run_simulator_shadow",
    "apply_decision_layer_rules",
    "run_simulator_shadow_multi",
    "slice_rows_by_date",
    "generate_rolling_windows",
    "build_multi_summary",
    "compute_rule_set_deltas",
    "extract_stability_band_insights",
    "extract_regime_insights",
    "extract_portfolio_type_insights",
    "build_calibration_summary",
    "build_consolidated_calibration_report",
    "rank_top_opportunities",
    "rank_top_risks",
    "identify_rule_refinement_targets",
    "identify_low_value_refinement_areas",
    "compute_signal_strength_score",
    "compute_stability_sensitivity_score",
    "compute_regime_sensitivity_score",
    "compute_portfolio_type_impact_score",
    "evaluate_rule_set_impact",
    "analyze_rule_set_impact",
    "generate_calibration_recommendations",
    "describe_calibration_export_contract",
    "export_for_daily_delta_tracker",
    "export_for_logic_dashboard",
    # Phase 4A + Phase 4B + Phase 4C + Phase 4D + Phase 4E + Phase 4F + Phase 4G + Phase 4H + Phase 4I + Phase 4J + Phase 4K
    # (isolated module – Phase 3/4A–4K code paths must never import or reference Phase 4I/4J/4K UI layer)
    "narrative",
    # Phase 4K Friend Mode (thin presenters only – logic lives in narrative.py)
    "get_friend_view_data",
    "build_friend_note",
    "FRIEND_LANGUAGE_VERSION",
    # Phase 4L Decision Surface (new)
    "get_hero_decision_band_data",
]