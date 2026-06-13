"""
Postprocessing step (Phase 3 minimal v1).

Responsibilities:
- Convert rich internal TickerScore objects into the stable export-oriented
  ScorecardRow format.
- Perform only lightweight, deterministic enrichment (abstention parsing,
  simple rocket_zone bucketing).
- Centralize the mapping rules so the ScorecardRow contract is easy to review
  and evolve deliberately.

v1 Conservative Choices:
- rocket_zone: simple ternary ("Positive" / "Neutral" / "Negative")
- abstention_status: promoted to first-class column (parsed from notes)
- New columns: final_rank, bandits_rocket, abstention_status, rocket_zone
- Layer 1 Abstention Reasoning: abstention_risk, abstention_reason, abstention_details
  are computed by inspecting TickerScore vs ScoringConfig. All factors captured.
  vNext: Catalyst Override + Volatility Context can downgrade high_atr_pct / high_stm
  severity (High→Medium) when catalyst + momentum + Rocket align with healthy vol context.
  See _compute_abstention_reasoning and abstention helpers.
- All other rich diagnostics (NewsPulse, full Rocket commentary, etc.) remain
  inside the `notes` field.
- Construction logic lives in ScorecardRow.from_ticker_score for better
  encapsulation.
"""

from __future__ import annotations

from typing import List, Optional

from engine.models.core import TickerScore, EngineConfig
from engine.models.scorecard import ScorecardRow

# v1.0 Corporate Actions context builder (live module)
try:
    from engine.pipeline.steps.corporate_actions import build_corporate_action_context
except Exception:
    build_corporate_action_context = None

# Catalyst Override + Volatility Context helpers (from abstention module)
try:
    from engine.pipeline.steps.scoring.abstention import (
        _should_apply_catalyst_override,
        _classify_volatility_context,
    )
except Exception:
    _should_apply_catalyst_override = None
    _classify_volatility_context = None

# v5 Transitional + Adaptive helpers (defined here for scope in postprocess)
def _is_in_transitional_improvement(score: "TickerScore") -> bool:
    """
    Returns True when multiple signals show clear improvement even if absolute levels are still weak.
    This is the key "regime transition" detector (per Briefing v5).
    """
    rs_improving = (getattr(score, "rs_acceleration", 0) or 0) > 0.02
    momentum_rising = (getattr(score, "momentum_pulse", 0) or 0) > 15
    rsi_improving = (getattr(score, "rsi_acceleration", 0) or 0) > 3.0
    improving_signals = sum([rs_improving, momentum_rising, rsi_improving])
    return improving_signals >= 2

def apply_adaptive_risk_decay(score: "TickerScore", current_risk: str) -> str:
    """
    Downgrades overall abstention_risk when clear transitional improvement is present.
    This prevents 'sticky bearishness'.
    """
    if current_risk != "High":
        return current_risk
    if _is_in_transitional_improvement(score):
        if (getattr(score, "momentum_pulse", 0) or 0) > 20 and (getattr(score, "bandits_rocket", 0) or 0) > 0:
            return "Medium"
    return current_risk


def _is_chaotic_high_vol(score: "TickerScore") -> bool:
    """
    Regime detector for the cohort where empirical forward data showed excellent
    returns despite (or because of) high volatility + poor absolute RS.

    Evidence (from chaotic_high_vol cohort, n=45):
        avg forward 12w return +112.38%, median +102.85%, max DD only -19.4% (contained).

    Used to relax breadth (and potentially other) penalties that would otherwise
    keep the engine at 0.0 / High in regimes that historically still delivered
    strong asymmetric upside.
    """
    atr = float(getattr(score, "feat_atr_pct", 0) or 0)
    rs = float(getattr(score, "feat_rs_vs_spy", 0) or 0)
    # Aligns with the analyzer cohort definition + "High risk / chaotic technical"
    return atr > 5.0 and rs < 0.85


def _parse_abstention_status(notes: str) -> Optional[str]:
    """
    Extract the abstention status from the notes field.

    Expected format (conservative): "Abstention: Trade Eligible | Rocket: ..."
    Falls back gracefully if the pattern is not found.
    """
    if not notes or "Abstention:" not in notes:
        return None

    try:
        # Take everything after "Abstention:" up to the first "|"
        after = notes.split("Abstention:", 1)[1]
        status = after.split("|", 1)[0].strip()
        return status or None
    except Exception:
        return None


def _compute_rocket_zone(rocket: Optional[float]) -> Optional[str]:
    """
    Simple ternary rocket_zone for v1.
    Thresholds are intentionally loose and can be refined later.
    """
    if rocket is None:
        return None
    if rocket > 0.5:
        return "Positive"
    if rocket < -0.5:
        return "Negative"
    return "Neutral"


def _get_scoring_thresholds(config: Optional[EngineConfig] = None) -> dict:
    """
    Extract abstention thresholds from EngineConfig.scoring (or fall back to defaults).
    Centralized so the reasoning logic stays in sync with get_abstention_status.
    """
    try:
        if config is not None and hasattr(config, "scoring") and config.scoring is not None:
            sc = config.scoring
            return {
                "min_momentum": float(getattr(sc, "min_momentum_pulse", 1.5)),
                "max_atr": float(getattr(sc, "max_atr_pct", 4.0)),
                "min_rs": float(getattr(sc, "min_rs_vs_spy", 0.85)),
                "min_breadth": float(getattr(sc, "min_breadth", 35.0)),
                "max_stm": float(getattr(sc, "max_stm", 45.0)),
                "min_adx": float(getattr(sc, "min_adx_for_trend", 18.0)),
            }
    except Exception:
        pass

    # Fallback to module defaults (import here to avoid top-level cycles during early load)
    try:
        from engine.pipeline.steps.scoring.scoring_config import DEFAULT_SCORING_CONFIG as _DEF
        sc = _DEF
        return {
            "min_momentum": float(sc.min_momentum_pulse),
            "max_atr": float(sc.max_atr_pct),
            "min_rs": float(sc.min_rs_vs_spy),
            "min_breadth": float(sc.min_breadth),
            "max_stm": float(sc.max_stm),
            "min_adx": float(sc.min_adx_for_trend),
        }
    except Exception:
        # Hardcoded last-resort (match current defaults)
        return {
            "min_momentum": 1.5,
            "max_atr": 4.0,
            "min_rs": 0.85,
            "min_breadth": 35.0,
            "max_stm": 45.0,
            "min_adx": 18.0,
        }


def _compute_abstention_reasoning(
    score: TickerScore, config: Optional[EngineConfig] = None
) -> tuple[Optional[str], str, list[dict]]:
    """
    Layer 1 Abstention Reasoning.

    Inspects the TickerScore's feature values against the active ScoringConfig
    thresholds and collects *all* contributing negative factors (no silent drop).

    - Factors are tagged with risk/severity based on how far they violate
      (e.g. the *0.6 / *1.5 "hard" observe triggers are High).
    - Sorted by risk (High > Medium > Low).
    - Overall abstention_risk is the highest-severity factor present (or "Low"
      when no violating factors, i.e. "Trade Eligible" case).
    - abstention_reason is a compact human string for CLI.
    - abstention_details is the full list[dict] (machine readable, for export /
      future backtesting and tuning).

    This is intentionally simple / rule-based and mirrors the structure of
    get_abstention_status so it can evolve together. New factors can be added
    over time as runs reveal patterns (per design principles).
    """
    t = _get_scoring_thresholds(config)
    min_m = t["min_momentum"]
    max_a = t["max_atr"]
    min_r = t["min_rs"]
    min_b = t["min_breadth"]
    max_s = t["max_stm"]
    min_ad = t["min_adx"]

    details: list[dict] = []

    # Pull values (defensive; TickerScore always has them as floats)
    mp = float(getattr(score, "momentum_pulse", 0.0))
    rs = float(getattr(score, "rs_vs_spy", 0.0))
    breadth = float(getattr(score, "relative_breadth_score", 50.0))
    atr = float(getattr(score, "atr_pct", 0.0))
    adx = float(getattr(score, "adx", 20.0))
    stm = float(getattr(score, "short_term_movement_intensity", 0.0))

    # === Hard / Observe-level violations (high risk) ===
    if mp < min_m * 0.6:
        details.append({
            "factor": "momentum_pulse_below_threshold",
            "value": round(mp, 2),
            "threshold": round(min_m * 0.6, 2),
            "severity": "high",
            "risk": "High",
        })
    elif mp < min_m:
        details.append({
            "factor": "momentum_pulse_below_threshold",
            "value": round(mp, 2),
            "threshold": round(min_m, 2),
            "severity": "medium",
            "risk": "Medium",
        })

    if rs < min_r * 0.8:
        details.append({
            "factor": "low_rs_vs_spy",
            "value": round(rs, 2),
            "threshold": round(min_r * 0.8, 2),
            "severity": "high",
            "risk": "High",
        })
    elif rs < min_r:
        details.append({
            "factor": "low_rs_vs_spy",
            "value": round(rs, 2),
            "threshold": round(min_r, 2),
            "severity": "medium",
            "risk": "Medium",
        })

    if breadth < min_b * 0.6:
        details.append({
            "factor": "low_relative_breadth",
            "value": round(breadth, 1),
            "threshold": round(min_b * 0.6, 1),
            "severity": "high",
            "risk": "High",
        })
    elif breadth < min_b:
        details.append({
            "factor": "low_relative_breadth",
            "value": round(breadth, 1),
            "threshold": round(min_b, 1),
            "severity": "medium",
            "risk": "Medium",
        })

    if atr > max_a * 1.5:
        details.append({
            "factor": "high_atr_pct",
            "value": round(atr, 2),
            "threshold": round(max_a * 1.5, 2),
            "severity": "high",
            "risk": "High",
        })
    elif atr > max_a:
        details.append({
            "factor": "high_atr_pct",
            "value": round(atr, 2),
            "threshold": round(max_a, 2),
            "severity": "medium",
            "risk": "Medium",
        })

    # === Minimal Direction contributors ===
    if adx < min_ad:
        details.append({
            "factor": "low_adx",
            "value": round(adx, 1),
            "threshold": round(min_ad, 1),
            "severity": "low",
            "risk": "Low",
        })

    # The combined condition in abstention for high chop + vol
    if stm > max_s and atr > max_a * 0.8:
        details.append({
            "factor": "high_stm_with_vol",
            "value": round(stm, 1),
            "threshold": round(max_s, 1),
            "severity": "medium",
            "risk": "Medium",
            "context": f"atr={round(atr, 2)}",
        })
    elif stm > max_s:
        details.append({
            "factor": "high_stm",
            "value": round(stm, 1),
            "threshold": round(max_s, 1),
            "severity": "low",
            "risk": "Low",
        })

    # === Catalyst Override + Volatility Context (per Current State Briefing) ===
    # When strong catalyst + momentum + positive Rocket align *and* the volatility
    # context is healthy ("expansion_with_trend"), we downgrade the severity of
    # high_atr_pct / high_stm / high_stm_with_vol factors (High → Medium).
    # This prevents the abstention layer from hard-vetoing healthy trend expansions
    # (the specific DOCN May–June 2026 failure mode).
    # Also supports "improving RS" to relax low_rs_vs_spy when recent relative performance is positive.
    override_applied = False
    if _should_apply_catalyst_override is not None and _classify_volatility_context is not None:
        try:
            cfg_for_override = getattr(config, "scoring", None) if config else None
            from engine.pipeline.steps.scoring.scoring_config import ScoringConfig
            if cfg_for_override is None:
                cfg_for_override = ScoringConfig()

            if _should_apply_catalyst_override(score, cfg_for_override):
                vol_context = _classify_volatility_context(score)
                if vol_context == "expansion_with_trend":
                    for d in details:
                        if d.get("factor") in ("high_atr_pct", "high_stm", "high_stm_with_vol"):
                            if d.get("risk") == "High":
                                d["risk"] = "Medium"
                                d["severity"] = "medium"
                                d["context"] = (d.get("context", "") + " [catalyst_override]").strip()
                                override_applied = True
                    if override_applied:
                        details.append({
                            "factor": "catalyst_override_applied",
                            "value": round(getattr(score, "catalyst_strength_score", 0.0) or 0.0, 3),
                            "severity": "info",
                            "risk": "Low",
                            "context": "Catalyst override applied – downgraded due to strong catalyst + improving RS + positive momentum",
                        })
        except Exception:
            # Never let the override logic break the main abstention path
            pass

    # Additional: if RS is improving (even if current level low), downgrade low_rs_vs_spy too
    rs_impr = getattr(score, "rs_improvement", 0.0) or 0.0
    if rs_impr > 0.01:
        for d in details:
            if d.get("factor") == "low_rs_vs_spy" and d.get("risk") == "High":
                d["risk"] = "Medium"
                d["severity"] = "medium"
                d["context"] = (d.get("context", "") + " [improving_rs]").strip()
                override_applied = True
        if rs_impr > 0.01 and not any(d.get("factor") == "catalyst_override_applied" for d in details):
            details.append({
                "factor": "catalyst_override_applied",
                "value": round(getattr(score, "catalyst_strength_score", 0.0) or 0.0, 3),
                "severity": "info",
                "risk": "Low",
                "context": "Catalyst override applied – downgraded due to strong catalyst + improving RS + positive momentum",
            })

    # v5 Chaotic High Vol breadth relaxation (based on empirical cohort evidence)
    # In regimes where high ATR + weak RS historically still produced strong forward returns
    # with contained drawdowns, we down-weight the low_relative_breadth penalty.
    # This prevents over-defensive 0.0/High outcomes on asymmetric opportunities in chaotic regimes.
    if _is_chaotic_high_vol(score):
        breadth_val = float(getattr(score, "relative_breadth_score", 50.0) or 50.0)
        breadth_relaxed = False
        for d in details:
            if d.get("factor") == "low_relative_breadth" and d.get("risk") == "High":
                d["risk"] = "Medium"
                d["severity"] = "medium"
                d["context"] = (d.get("context", "") + " [chaotic_regime_relax]").strip()
                breadth_relaxed = True
        if breadth_relaxed:
            details.append({
                "factor": "breadth_relaxed_chaotic",
                "value": round(breadth_val, 1),
                "severity": "info",
                "risk": "Low",
                "context": "Breadth penalty relaxed – chaotic high-vol cohort delivered +112% avg fwd with contained DD",
            })

    # v5 transitional block moved after overall computation to avoid unbound variable (see below)

    if not details:
        # Clean / Trade Eligible path
        return "Low", "", []

    # Risk ordering: highest first (stable for equal risk)
    risk_order = {"High": 3, "Medium": 2, "Low": 1}
    sorted_d = sorted(
        details,
        key=lambda d: (risk_order.get(d.get("risk", "Low"), 0), d.get("value", 0)),
        reverse=True,
    )

    # Human reason (matches example style)
    parts: list[str] = []
    for d in sorted_d:
        val = d["value"]
        if "context" in d:
            parts.append(f"{d['factor']} ({val}, {d['context']})")
        else:
            parts.append(f"{d['factor']} ({val})")
    reason = " + ".join(parts)

    # Overall = highest risk present
    if any(d.get("risk") == "High" for d in sorted_d):
        overall = "High"
    elif any(d.get("risk") == "Medium" for d in sorted_d):
        overall = "Medium"
    else:
        overall = "Low"

    # === Decisive global Medium cap (per Final Refinement spec) ===
    # When full aligned signals + healthy expansion context, force risk to Medium
    # (global cap) so the engine actually participates on high-quality trend days.
    # This is the decisive step: per-factor downgrades are advisory/transparency;
    # this cap makes the override effective for cases like DOCN May–June.
    # Only cap High -> Medium; never upgrade Low. Never override hard chaotic vetoes
    # (the _should_apply + classify conditions already exclude negative momentum/rocket etc.).
    try:
        cfg_for_override = getattr(config, "scoring", None) if config else None
        from engine.pipeline.steps.scoring.scoring_config import ScoringConfig
        if cfg_for_override is None:
            cfg_for_override = ScoringConfig()

        if (_should_apply_catalyst_override is not None and
            _classify_volatility_context is not None and
            _should_apply_catalyst_override(score, cfg_for_override) and
            _classify_volatility_context(score) == "expansion_with_trend"):
            if overall == "High":
                overall = "Medium"
                cap_note = "Catalyst override applied – global Medium cap due to strong catalyst + improving RS + positive momentum + healthy expansion context"
                # Add auditable entry to details (for JSON/CSV)
                details.append({
                    "factor": "catalyst_override_global_cap",
                    "value": round(getattr(score, "catalyst_strength_score", 0.0) or 0.0, 3),
                    "severity": "info",
                    "risk": "Medium",
                    "context": cap_note,
                })
                # Update reason for human readability (include in abstention_reason)
                if "catalyst_override_global_cap" not in reason:
                    reason = (reason + " + catalyst_override_global_cap") if reason else "catalyst_override_global_cap"
                # Also ensure the note is in the original details list for the returned value
                # (sorted_d is a snapshot; caller uses the returned details too)
    except Exception:
        # Defensive: never break the reasoning path
        pass

    return overall, reason, sorted_d


# =============================================================================
# Exposure Scaling v3 (per Exposure Scaling Briefing v3)
# Computes graduated position size (0.0 / 0.25 / 0.5 / 1.0) after the
# Catalyst Override + global Medium cap logic.
# Risk now modulates size, not just the binary go/no-go.
# =============================================================================

def compute_exposure_scale(score: TickerScore, cfg: ScoringConfig) -> float:
    """Returns 0.0, 0.25, 0.50, or 1.0 based on regime strength.

    Follows the exact mapping in Exposure Scaling Briefing v3:
    - 0% for chaotic / hard-veto (High abstention without override)
    - 25% for probing / borderline (override fires but not elite)
    - 50% for standard swing (good alignment + healthy expansion)
    - 100% for full conviction (elite thresholds + improving RS + expansion context)
    """
    # Chaotic / hard-veto regimes (preserve existing hard logic)
    if getattr(score, "abstention_risk", None) == "High" and not _should_apply_catalyst_override(score, cfg):
        return 0.0

    # Override conditions fully met + healthy expansion context
    if _should_apply_catalyst_override(score, cfg) and _classify_volatility_context(score) == "expansion_with_trend":
        mom = getattr(score, "momentum_pulse", 0.0) or 0.0
        rocket = getattr(score, "bandits_rocket", 0.0) or 0.0
        if mom >= getattr(cfg, "momentum_full_conviction_threshold", 50.0) and rocket >= getattr(cfg, "rocket_full_conviction_threshold", 3.0):
            return 1.0
        elif mom >= 25.0:
            return 0.5
        else:
            return 0.25

    # Positive but not elite regime
    if getattr(score, "abstention_risk", None) in ("Medium", "Low"):
        mom = getattr(score, "momentum_pulse", 0.0) or 0.0
        return 0.25 if mom < 15.0 else 0.5

    # v5: Transitional improvement can bump exposure even in borderline cases
    if _is_in_transitional_improvement is not None and _is_in_transitional_improvement(score):
        if (getattr(score, "momentum_pulse", 0) or 0) > 15 and (getattr(score, "bandits_rocket", 0) or 0) > 0:
            return 0.5

    return 0.0


# =============================================================================
# Rolling 12-Week Calibration Tracking & Hit-Rate Logging (per Briefing v4)
# Lightweight, replay-native snapshot for forward performance measurement.
# Called from replay when full_export=True. Forward returns populated later
# via post-replay shift or dedicated script.
# =============================================================================

def log_calibration_snapshot(
    score: TickerScore,
    forward_12w_return: Optional[float] = None,
    forward_12w_max_dd: Optional[float] = None,
    cfg: Optional[ScoringConfig] = None,
    abstention_risk: Optional[str] = None,
    rocket_zone: Optional[str] = None,
) -> dict:
    """
    Returns a compact calibration record for logging / CSV export.
    Called inside the replay loop after postprocess() when full_export=True.
    """
    cfg = cfg or ScoringConfig()
    ar = abstention_risk or getattr(score, "abstention_risk", None)
    rz = rocket_zone or getattr(score, "rocket_zone", None)
    cat_strength = getattr(score, "catalyst_strength_score", None)
    mom = getattr(score, "momentum_pulse", None)
    rocket = getattr(score, "bandits_rocket", None)
    exposure = getattr(score, "exposure_scale", None)
    details_str = str(getattr(score, "abstention_details", []) or getattr(score, "notes", "") or "")

    return {
        "date": getattr(score, "as_of", None),  # or pass explicitly if needed
        "ticker": getattr(score, "ticker", None),
        "exposure_scale": exposure,
        "abstention_risk": ar,
        "rocket_zone": rz,
        "catalyst_strength_score": cat_strength,
        "momentum_pulse": mom,
        "bandits_rocket": rocket,
        "forward_12w_return_pct": forward_12w_return,
        "forward_12w_max_dd_pct": forward_12w_max_dd,
        "diagnostic_labels": _generate_diagnostic_labels(score, ar, exposure, cat_strength, mom, rocket),
        "catalyst_override_applied": "catalyst_override_applied" in details_str,
        "global_cap_applied": "catalyst_override_global_cap" in details_str,
    }


def _generate_diagnostic_labels(
    score: TickerScore,
    abstention_risk: Optional[str] = None,
    exposure_scale: Optional[float] = None,
    catalyst_strength: Optional[float] = None,
    momentum: Optional[float] = None,
    rocket: Optional[float] = None,
) -> list[str]:
    labels = []
    ar = abstention_risk or getattr(score, "abstention_risk", None)
    exp = exposure_scale if exposure_scale is not None else getattr(score, "exposure_scale", None)
    cat = catalyst_strength if catalyst_strength is not None else getattr(score, "catalyst_strength_score", None)
    mom = momentum if momentum is not None else getattr(score, "momentum_pulse", None)
    rkt = rocket if rocket is not None else getattr(score, "bandits_rocket", None)

    if ar == "High" and (exp == 0.0 or exp is None):
        if (mom or 0) < -15:
            labels.append("MOMENTUM_EXHAUSTION")
        if (rkt or 0) < 0:
            labels.append("ROCKET_NEGATIVE")
        # Add more as patterns emerge (e.g. REGIME_MISMATCH)
    if exp == 1.0 and (getattr(score, "atr_pct", 0) or 0) > 6.5:
        labels.append("HIGH_VOL_TREND_ACCEPTED")
    if (cat or 0) >= 0.40:
        labels.append("CATALYST_DRIVEN")
    if "catalyst_override_applied" in str(getattr(score, "abstention_details", []) or ""):
        labels.append("CATALYST_OVERRIDE_APPLIED")
    if (getattr(score, "rs_acceleration", 0) or 0) > 0.02 or (getattr(score, "feat_rs_acceleration", 0) or 0) > 0.02:
        labels.append("RS_ACCELERATING")
    if any(d.get("factor") == "breadth_relaxed_chaotic" for d in (getattr(score, "abstention_details", []) or [])):
        labels.append("BREADTH_RELAXED_CHAOTIC")
    elif "breadth_relaxed_chaotic" in str(getattr(score, "abstention_details", "") or ""):
        labels.append("BREADTH_RELAXED_CHAOTIC")
    return labels


def postprocess(
    scores: List[TickerScore],
    config: EngineConfig | None = None,
    corporate_actions: Optional[dict[str, dict]] = None,  # v1.0 rich per-ticker from live module
) -> List[ScorecardRow]:
    """
    Minimal Phase 3 postprocess step.

    Converts TickerScore (internal engine model) into ScorecardRow
    (export / archive model).

    v1.0: Accepts corporate_actions dict to build unified context + enrich notes.
    This is intentionally lightweight. Heavy logic belongs in the scoring
    layer or future postprocess expansions.
    """
    if not scores:
        return []

    rows: List[ScorecardRow] = []

    for s in scores:
        abstention = _parse_abstention_status(s.notes)
        rocket_zone = _compute_rocket_zone(s.bandits_rocket)

        # Layer 1 abstention reasoning (all factors, risk ordered)
        risk, reason, details = _compute_abstention_reasoning(s, config)

        # Improve visibility: append clear human note to notes when override (incl. global cap) fired (appears in scorecard_notes / CSV)
        override_factors = {"catalyst_override_applied", "catalyst_override_global_cap"}
        if any(d.get("factor") in override_factors for d in (details or [])):
            # Prefer the global cap note if present, else the per-factor one
            cap_d = next((d for d in (details or []) if d.get("factor") == "catalyst_override_global_cap"), None)
            note = cap_d.get("context") if cap_d else "Catalyst override applied – downgraded due to strong catalyst + improving RS + positive momentum"
            if note not in (s.notes or ""):
                s.notes = ((s.notes or "") + " | " + note).strip(" |")

        # Exposure Scaling v3 (after override/global cap)
        scoring_cfg = getattr(config, "scoring", None) or ScoringConfig()
        exposure_scale = compute_exposure_scale(s, scoring_cfg)
        s.exposure_scale = exposure_scale  # attach to TickerScore for downstream

        # v4 Calibration snapshot (replay-native; forwards=None for now, populated later)
        cal_record = log_calibration_snapshot(
            s, None, None, scoring_cfg, risk, rocket_zone
        )
        s.calibration_record = cal_record  # attach for replay to pick up

        # v1.0 Corporate Actions context (protective, contextual, not primary score driver)
        ca_context: Optional[dict] = None
        if corporate_actions and build_corporate_action_context is not None:
            ca = corporate_actions.get(s.ticker.upper()) or corporate_actions.get(s.ticker)
            if ca:
                try:
                    ca_context = build_corporate_action_context(ca)
                    # Enrich the score's notes with corp notes for interpretability (append to existing)
                    corp_notes = ca_context.get("notes", []) or []
                    if corp_notes:
                        existing = (getattr(s, "notes", "") or "").strip()
                        extra = " | ".join(corp_notes)
                        s.notes = (existing + (" | " if existing else "") + f"CorpActions: {extra}").strip()

                    # Add CA abstention hooks / reasons (v1.0) to details for downstream abstention engine
                    if ca_context.get("has_recent_split"):
                        details.append({
                            "factor": "recent_split_distortion",
                            "value": ca_context.get("split_date"),
                            "severity": "medium",
                            "risk": "Medium",
                        })
                    if ca_context.get("recent_dividend_cut"):
                        details.append({
                            "factor": "dividend_cut_risk",
                            "value": ca_context.get("dividend_cut_date"),
                            "severity": "high",
                            "risk": "High",
                        })
                    if ca_context.get("ex_div_date"):
                        details.append({
                            "factor": "ex_div_price_distortion",
                            "value": ca_context.get("ex_div_date"),
                            "severity": "low",
                            "risk": "Low",
                        })
                except Exception:
                    ca_context = None

        # v1.0: if CA introduced high-risk factors, bump overall risk/reason for abstention
        high_ca_factors = [d.get("factor") for d in details if d.get("risk") == "High" and d.get("factor") in ("recent_split_distortion", "dividend_cut_risk")]
        if high_ca_factors:
            risk = "High"
            reason = (reason or "") + (" + " if reason else "") + " + ".join(high_ca_factors)

        # Use the factory method for a clean, centralized mapping
        row = ScorecardRow.from_ticker_score(
            score=s,
            abstention_status=abstention,
            rocket_zone=rocket_zone,
            abstention_risk=risk,
            abstention_reason=reason,
            abstention_details=details,
            corporate_action_context=ca_context,
            exposure_scale=exposure_scale,
        )
        # Attach calibration for consumers that use the row directly
        if hasattr(s, "calibration_record"):
            row.calibration_record = s.calibration_record
        rows.append(row)

    return rows
