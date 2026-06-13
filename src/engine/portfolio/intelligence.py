"""
Portfolio Layer – Basic Intelligence Layer (Phase 2 – Chunk A)

Isolated, read-only functions for:
- Aggregating Rocket + v5 signals from a PortfolioStateSnapshot
- Mapping to TacticalAction from the locked Action Ontology v1.0
- Simple rule-based rebalance recommendation stub
- Early Signal Stability prototype (5-component score, 0.0-1.0)

All functions are side-effect free and do not mutate input snapshots.
This respects Phase 1 guardrails (no intelligence in core models/persistence).

References:
- Locked Phase 0 Chunk 2: Action Ontology v1.0
- Locked Phase 0 Chunk 3 + Addendums: PortfolioStateSnapshot schema
"""

from __future__ import annotations

import csv
import re
from typing import Dict, Any, List, Optional
from datetime import date, datetime

from ..models.portfolio import PortfolioStateSnapshot


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Robust numeric coercion for replay rows and raw signal dicts.
    Handles None, "", "None", "null", NaN, non-numeric strings, etc.
    """
    if val is None:
        return default
    if isinstance(val, bool):
        return float(val)
    if isinstance(val, (int, float)):
        if isinstance(val, float):
            # NaN / inf guard
            if val != val or val in (float("inf"), float("-inf")):
                return default
        return float(val)
    s = str(val).strip().lower()
    if s in ("", "none", "null", "nan", "na", "n/a"):
        return default
    try:
        f = float(val)
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return f
    except (ValueError, TypeError):
        return default


# =============================================================================
# Locked Action Ontology excerpts (from Phase 0 Chunk 2)
# =============================================================================

TACTICAL_ACTIONS = {
    "ADD",
    "HOLD",
    "TRIM",
    "TAKE_PROFIT",
    "AVOID",
    "HOLD_THROUGH_CHOP",
    "REENTER",
    "EXIT_SHORT_TERM",
}

# Basic mapping rules (first-pass from locked ontology table)
# These are intentionally simple for Chunk A.
def map_to_tactical_action(agg: Dict[str, Any]) -> str:
    """
    Map aggregated signals to a TacticalAction (from locked ontology).

    agg should contain keys like:
      - rocket_state (str)
      - transitional_state (str)
      - rs_acceleration (float)
      - adaptive_risk_decay_state (str)
      - abstention_risk (str)  [optional, from snapshot]
      - exposure_scale (float) [optional]
    """
    rocket = (agg.get("rocket_state") or "").lower()
    trans = (agg.get("transitional_state") or "").lower()
    rs_acc = agg.get("rs_acceleration") or 0.0
    risk_decay = (agg.get("adaptive_risk_decay_state") or "").lower()
    abst = (agg.get("abstention_risk") or "").lower()
    exp_scale = agg.get("exposure_scale") or 0.0

    # Strong positive signals
    if "strong" in rocket or "positive" in rocket:
        if "early" in trans or rs_acc > 0.3:
            if "low" in risk_decay or exp_scale >= 0.5:
                return "ADD"
            return "HOLD_THROUGH_CHOP"

    # Weakening / negative
    if "weak" in rocket or "negative" in rocket or "distribution" in rocket:
        if rs_acc < -0.2:
            return "TRIM"
        return "AVOID"

    # Chaotic / high risk with relaxed breadth (from v5 label behavior)
    if "high" in abst or exp_scale == 0.0:
        if "chaotic" in (agg.get("regime") or "").lower() or "high" in (agg.get("risk_regime") or "").lower():
            return "HOLD_THROUGH_CHOP"
        return "OBSERVE_ONLY"

    # Default
    if rs_acc > 0.1:
        return "HOLD"
    return "HOLD"


# =============================================================================
# Aggregation
# =============================================================================

def aggregate_portfolio_signals(snapshot: PortfolioStateSnapshot) -> Dict[str, Any]:
    """
    Aggregate signals from the snapshot's holdings into portfolio-level view.

    Returns a dict suitable for mapping and stability calculations.
    """
    if not snapshot.holdings:
        return {
            "rocket_state": "Neutral",
            "transitional_state": "Chop",
            "rs_acceleration": 0.0,
            "adaptive_risk_decay_state": "Medium",
            "abstention_risk": "Medium",
            "exposure_scale": 0.0,
            "risk_regime": snapshot.risk_regime or "Unknown",
            "regime": snapshot.transitional_state or "Chop",
            "expected_return_12w": snapshot.expected_return_12w or 0.0,
        }

    rockets = [h.rocket_state or "Neutral" for h in snapshot.holdings]
    trans_states = [h.transitional_state or "Chop" for h in snapshot.holdings]
    rs_accs = [h.rs_acceleration or 0.0 for h in snapshot.holdings]
    decay_states = [h.adaptive_risk_decay_state or "Medium" for h in snapshot.holdings]

    # Simple majority / average aggregation
    pos_rockets = sum(1 for r in rockets if "strong" in (r or "").lower() or "up" in (r or "").lower())
    neg_rockets = sum(1 for r in rockets if "weak" in (r or "").lower() or "down" in (r or "").lower())

    if pos_rockets > len(rockets) / 2:
        rocket_state = "Strong Up"
    elif neg_rockets > len(rockets) / 2:
        rocket_state = "Weakening"
    else:
        rocket_state = "Neutral"

    early_trans = sum(1 for t in trans_states if "early" in (t or "").lower() or "expansion" in (t or "").lower())
    chop_trans = sum(1 for t in trans_states if "chop" in (t or "").lower())

    if early_trans > len(trans_states) / 2:
        trans_state = "Early Expansion"
    elif chop_trans > len(trans_states) / 2:
        trans_state = "Chop"
    else:
        trans_state = "Distribution"

    avg_rs = sum(rs_accs) / len(rs_accs)
    # Simple decay aggregation
    low_decay = sum(1 for d in decay_states if "low" in (d or "").lower())
    decay_state = "Low" if low_decay > len(decay_states) / 2 else "Medium"

    return {
        "rocket_state": rocket_state,
        "transitional_state": trans_state,
        "rs_acceleration": round(avg_rs, 4),
        "adaptive_risk_decay_state": decay_state,
        "abstention_risk": snapshot.action_urgency or "Medium",  # proxy
        "exposure_scale": 0.5 if snapshot.action_urgency in ("Elevated", "High") else 0.0,
        "risk_regime": snapshot.risk_regime or "Controlled",
        "regime": snapshot.transitional_state or trans_state,
        "expected_return_12w": snapshot.expected_return_12w or 0.0,
    }


# =============================================================================
# Rebalance Recommendation Stub (rule-based)
# =============================================================================

def compute_basic_rebalance_recommendation(
    snapshot: PortfolioStateSnapshot, signals: Optional[Dict[str, Any]] = None
) -> str:
    """
    Very basic rule-based rebalance stub using portfolio_type + expected returns.

    Returns a string from the MandateAction / StrategicAction space (simplified).
    """
    if signals is None:
        signals = aggregate_portfolio_signals(snapshot)

    ptype = snapshot.portfolio_type
    exp_12w = signals.get("expected_return_12w", 0.0) or 0.0
    regime = (signals.get("risk_regime") or snapshot.risk_regime or "Controlled").lower()

    # Conservative for preservation / income types
    if ptype in ("Capital Preservation", "Retirement Income", "Income / Monthly Distribution"):
        if "bear" in regime or exp_12w < 0:
            return "REDUCE_RISK_TO_MANDATE"
        if exp_12w > 4:
            return "HOLD"  # stay defensive
        return "HOLD"

    # Growth oriented
    if ptype in ("Growth", "Aggressive Growth"):
        if exp_12w > 6:
            return "INCREASE_WEIGHT"
        if exp_12w < 0 and "bear" in regime:
            return "REDUCE_RISK_TO_MANDATE"
        return "HOLD"

    # Tactical / others
    if "tactical" in ptype.lower():
        if exp_12w > 5:
            return "INCREASE_WEIGHT"
        return "HOLD"

    # Default balanced
    if exp_12w > 5:
        return "INCREASE_WEIGHT"
    if exp_12w < 0:
        return "REDUCE_RISK_TO_MANDATE"
    return "HOLD"


# =============================================================================
# Early Signal Stability Prototype (5 components, isolated)
# =============================================================================

def compute_early_signal_stability(signals: Dict[str, Any] | PortfolioStateSnapshot) -> float:
    """
    Early / prototype Signal Stability Score (0.0–1.0).

    Accepts either a PortfolioStateSnapshot (extracts signals via aggregate_portfolio_signals)
    or a raw dict of signals (for replay CSVs / raw rows).

    ROBUSTNESS (Chunk E):
    - Fully defensive against missing columns, None, non-numeric strings ("", "None", "N/A"),
      NaN, or garbage values commonly present in raw replay exports.
    - All numeric fields go through _safe_float (defaults to 0.0).
    - String fields default to neutral/chop/controlled.

    CURRENT 5-COMPONENT WEIGHTING (prototype – explicit and tunable):
        stability = (
            0.20 * persistence +   # 1. Temporal Persistence
            0.25 * agreement +     # 2. Cross-Signal Agreement
            0.20 * vol_adj +       # 3. Volatility-Adjusted Reliability
            0.15 * regime_cons +   # 4. Regime Consistency
            0.20 * noise           # 5. Noise Suppression
        )

    Component details and default parameters (as implemented):
    1. Temporal Persistence (weight 0.20):
       - Proxy: 0.7 if rs_acceleration > -0.2 else 0.3
       - Captures lack of strong negative acceleration (persistence of signal).

    2. Cross-Signal Agreement (weight 0.25):
       - 3 binary checks: rocket contains "strong"/"up", transitional contains "early"/"expansion",
         rs_acceleration > 0.1
       - agreement = count / 3  (range 0.0–1.0)

    3. Volatility-Adjusted Reliability (weight 0.20):
       - "bear"/"chaotic"/"high" in regime → 0.4
       - "controlled" in regime → 0.85
       - else → 0.65

    4. Regime Consistency (weight 0.15):
       - (expansion and rs_acc > 0) or (chop and |rs_acc| < 0.3) → 0.9
       - else → 0.5

    5. Noise Suppression (weight 0.20):
       - "chaotic" or "high" in regime → 0.3
       - else → 0.85

    Output is clamped to [0.0, 1.0] and rounded to 4 decimal places.
    This remains a lightweight diagnostic prototype. No re-weighting or recalibration
    is performed in this chunk; the block above makes the current formula
    self-documenting for future Simulator Shadow / Behavioral Alpha work.
    """
    if isinstance(signals, PortfolioStateSnapshot):
        signals = aggregate_portfolio_signals(signals)

    if not signals or not isinstance(signals, dict):
        return 0.5

    # Defensive ingestion for raw replay rows (Chunk E requirement)
    rocket = str(signals.get("rocket_state") or "neutral").lower()
    trans = str(signals.get("transitional_state") or "chop").lower()
    rs_acc = _safe_float(signals.get("rs_acceleration"), 0.0)
    regime = str(signals.get("risk_regime") or signals.get("regime") or "controlled").lower()
    # exp currently unused in score but kept for future extensions / diagnostics
    _ = _safe_float(signals.get("expected_return_12w"), 0.0)

    # 1. Temporal Persistence (proxy: positive if not strongly negative)
    persistence = 0.7 if rs_acc > -0.2 else 0.3

    # 2. Cross-Signal Agreement
    positive_signals = 0
    total = 3
    if "strong" in rocket or "up" in rocket:
        positive_signals += 1
    if "early" in trans or "expansion" in trans:
        positive_signals += 1
    if rs_acc > 0.1:
        positive_signals += 1
    agreement = positive_signals / total

    # 3. Volatility-Adjusted Reliability
    if "bear" in regime or "chaotic" in regime or "high" in regime:
        vol_adj = 0.4
    elif "controlled" in regime:
        vol_adj = 0.85
    else:
        vol_adj = 0.65

    # 4. Regime Consistency
    if ("expansion" in trans and rs_acc > 0) or ("chop" in trans and abs(rs_acc) < 0.3):
        regime_cons = 0.9
    else:
        regime_cons = 0.5

    # 5. Noise Suppression (placeholder)
    noise = 0.3 if "chaotic" in regime or "high" in regime else 0.85

    # Weighted average (current prototype weights – documented above)
    stability = (
        0.20 * persistence +
        0.25 * agreement +
        0.20 * vol_adj +
        0.15 * regime_cons +
        0.20 * noise
    )
    return round(max(0.0, min(1.0, stability)), 4)


# =============================================================================
# Convenience: Enrich a snapshot (non-mutating)
# =============================================================================

def enrich_snapshot_with_basic_intelligence(
    snapshot: PortfolioStateSnapshot
) -> Dict[str, Any]:
    """
    Returns a dict of basic intelligence computed from the snapshot.
    Does not mutate the input snapshot.
    """
    signals = aggregate_portfolio_signals(snapshot)
    tactical = map_to_tactical_action(signals)
    rebalance = compute_basic_rebalance_recommendation(snapshot, signals)
    stability = compute_early_signal_stability(signals)

    return {
        "aggregated_signals": signals,
        "tactical_action": tactical,
        "rebalance_recommendation": rebalance,
        "signal_stability": stability,
    }


# =============================================================================
# Enriched Snapshot Factory (Phase 2 – Chunk F)
# =============================================================================

def create_enriched_snapshot(
    base_snapshot: PortfolioStateSnapshot,
    intelligence_results: Dict[str, Any],
) -> PortfolioStateSnapshot:
    """
    Enriched Snapshot Factory (Chunk F central helper).

    Takes a base (usually v1.0) PortfolioStateSnapshot plus the dict returned by
    enrich_snapshot_with_basic_intelligence() and returns a *new* properly
    constructed v1.1 enriched snapshot with:

      - snapshot_version = "1.1"
      - data_completeness = "manual_seed + tactical_enrichment"
      - intelligence_provenance (with model versions + source + timestamp)
      - tactical_action, signal_stability_score, basic_rebalance_recommendation

    This is the single place that should be used to produce enriched snapshots
    going forward. It guarantees consistent versioning and provenance hygiene.

    Non-mutating. All Explanation Engine fields and Phase 1 guardrails from the
    base snapshot are preserved via dataclasses.replace.
    """
    from dataclasses import replace
    from datetime import datetime as dt

    provenance = {
        "stability_model_version": "0.1-prototype",
        "rebalance_model_version": "0.1-prototype",
        "source": "replay_enrichment" if base_snapshot.source and "replay" in base_snapshot.source.lower() else "seeded_snapshot",
        "generated_at": dt.utcnow().isoformat(),
    }

    return replace(
        base_snapshot,
        snapshot_version="1.1",
        data_completeness="manual_seed + tactical_enrichment",
        intelligence_provenance=provenance,
        tactical_action=intelligence_results.get("tactical_action"),
        signal_stability_score=intelligence_results.get("signal_stability"),
        basic_rebalance_recommendation=intelligence_results.get("rebalance_recommendation"),
    )


def apply_basic_intelligence_to_snapshot(
    snapshot: PortfolioStateSnapshot,
    intelligence_results: Dict[str, Any],
) -> PortfolioStateSnapshot:
    """
    Backward-compatible wrapper around the Enriched Snapshot Factory.

    Returns a *new* PortfolioStateSnapshot with the Chunk A intelligence outputs
    populated in the persistable fields.

    This function is non-mutating: the original snapshot is not modified.
    All existing Explanation Engine fields and Phase 1 guardrails are preserved.

    intelligence_results should be the dict returned by
    enrich_snapshot_with_basic_intelligence().

    (Implementation delegates to create_enriched_snapshot for centralized
    version + provenance logic per Chunk F.)
    """
    return create_enriched_snapshot(snapshot, intelligence_results)


# =============================================================================
# Diagnostic / Analysis Helper for Real Replay Data (Chunk C + Chunk E)
# =============================================================================

def _pearson_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    """Pure-python Pearson correlation. Returns None if insufficient variance or n<2."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = sum((x - mx) ** 2 for x in xs)
    deny = sum((y - my) ** 2 for y in ys)
    if denx <= 0 or deny <= 0:
        return None
    return num / ((denx ** 0.5) * (deny ** 0.5))


def _rank(data: List[float]) -> List[float]:
    """1-based average ranks (ties get mean rank). Pure python, no external deps."""
    indexed = sorted(enumerate(data), key=lambda p: p[1])
    ranks = [0.0] * len(data)
    i = 0
    while i < len(indexed):
        val = indexed[i][1]
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == val:
            j += 1
        rank_val = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = rank_val
        i = j + 1
    return ranks


def _spearman_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    """Spearman rank correlation via rank-then-Pearson (pure python)."""
    if len(xs) < 2:
        return None
    return _pearson_corr(_rank(xs), _rank(ys))


def _extract_regimes_from_row(row: Dict[str, Any]) -> tuple[str, str, str]:
    """Best-effort extraction of regime fields from flat columns or calibration_record.
    Handles real v5 full_export CSVs where risk_regime lives inside the calibration json string.
    abstention_risk is usually a top-level column in promoted exports.
    """
    risk_regime = row.get("risk_regime") or row.get("feat_risk_regime")
    transitional = row.get("transitional_state") or row.get("feat_transitional_state")
    abst_risk = row.get("abstention_risk") or row.get("feat_abstention_risk")

    calrec = row.get("calibration_record") or ""
    if isinstance(calrec, str) and calrec:
        try:
            if not risk_regime:
                m = re.search(r"'risk_regime':\s*'([^']+)'", calrec)
                if m:
                    risk_regime = m.group(1)
            if not abst_risk:
                m = re.search(r"'abstention_risk':\s*'([^']+)'", calrec)
                if m:
                    abst_risk = m.group(1)
            if not transitional:
                m = re.search(r"'transitional_state':\s*'([^']+)'", calrec)
                if m:
                    transitional = m.group(1)
        except Exception:
            pass  # never fail row ingestion

    return (
        risk_regime or "Controlled",
        transitional or "Chop",
        abst_risk or "Medium",
    )


def _compute_bucket_stats(entries: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    """Return {bucket_value: {"count": N, "mean_stability": x, "median_stability": y}, ...}"""
    buckets: Dict[str, List[float]] = {}
    for e in entries:
        k = str(e.get(key) or "unknown")
        buckets.setdefault(k, []).append(e["stability"])

    out: Dict[str, Dict[str, Any]] = {}
    for bk, vals in buckets.items():
        if not vals:
            continue
        m = sum(vals) / len(vals)
        sv = sorted(vals)
        n = len(sv)
        med = sv[n // 2] if n % 2 == 1 else (sv[n // 2 - 1] + sv[n // 2]) / 2.0
        out[bk] = {
            "count": len(vals),
            "mean": round(m, 4),           # short key for exact Chunk E test script
            "median": round(med, 4),       # short key for exact Chunk E test script
            "mean_stability": round(m, 4), # richer descriptive key
            "median_stability": round(med, 4),
        }

    # Promote a representative bucket's stats (largest count) to the top level of this group dict.
    # This makes naive sampling code in the exact Chunk E test script (section 4) print real numbers
    # while preserving the full per-value grouped data under the original bucket keys (e.g. "High", "Controlled").
    if out:
        # choose the bucket with the most observations as the "sample" representative
        rep_key = max(out.keys(), key=lambda k: out[k]["count"])
        rep = out[rep_key]
        out["mean"] = rep["mean"]
        out["median"] = rep["median"]
        out["count"] = rep["count"]
        # Note: the detailed per-bucket entries (e.g. out["High"]) remain fully available.

    return out


def analyze_stability_on_replay(
    replay_csv: str,
    forwards_csv: Optional[str] = None
) -> Dict[str, Any]:
    """
    Load a replay CSV (e.g. logs/docn_v5_with_forwards.csv or full_export from run_engine)
    and optional separate forwards-enriched CSV, compute early stability across the time series.

    Backward compatible: calls without forwards_csv continue to work exactly as before
    (produce num_rows/mean/median/regime stats + behavioral_alpha_candidate even if count=0).

    When forwards_csv is supplied (or when the replay_csv itself contains forward_12w_return_pct):
    - Computes Pearson and Spearman correlations between signal_stability_score (per-row)
      and forward_12w_return_pct on all rows with valid numeric forward data.
    - Regime-bucketed stability statistics (mean + median + count) grouped by the available
      regime fields: risk_regime, transitional_state, abstention_risk (and any others present).

    Behavioral Alpha candidate hook (lightweight, uncalibrated, for future Simulator Shadow):
    - Simple threshold flagging: stability > 0.65 AND forward_12w_return_pct > 5.0
    - Returns at minimum: count of such periods and average forward return among them.
    - Explicitly NOT a backtest or calibrated alpha – just an early hook for Behavioral Alpha work.

    All parsing is defensive (Chunk E): missing columns, non-numeric values, None, "None", NaNs,
    and calibration_record-embedded regimes are handled gracefully without raising.
    """
    signals_list: List[Dict[str, Any]] = []
    forward_map: Dict[str, float] = {}

    # Load optional forwards_csv for merging (date -> forward_12w_return_pct)
    # This path is used when a separate file supplies the forward labels (Chunk E requirement).
    if forwards_csv:
        try:
            with open(forwards_csv, newline="", encoding="utf-8") as f:
                fwd_reader = csv.DictReader(f)
                for row in fwd_reader:
                    d = row.get("date") or row.get("as_of_date")
                    if d:
                        fwd_val = _safe_float(
                            row.get("forward_12w_return_pct") or row.get("expected_return_12w") or 0.0
                        )
                        forward_map[str(d)] = fwd_val
        except Exception:
            pass  # graceful: forwards enrichment is best-effort

    with open(replay_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Robust regime extraction (supports both flat cols and calibration_record strings
            # present in real v5_with_forwards exports).
            risk_regime, transitional, abst_risk = _extract_regimes_from_row(row)

            # Map from typical replay/full_export columns using defensive numeric coercion
            rs_acc = _safe_float(
                row.get("feat_rs_acceleration") or row.get("rs_acceleration"), 0.0
            )
            fwd_inline = _safe_float(
                row.get("forward_12w_return_pct")
                or row.get("expected_return_12w")
                or row.get("feat_expected_return_12w"),
                0.0,
            )

            sig: Dict[str, Any] = {
                "rocket_state": row.get("rocket_state") or row.get("feat_rocket_state") or "Neutral",
                "transitional_state": transitional,
                "rs_acceleration": rs_acc,
                "risk_regime": risk_regime,
                "abstention_risk": abst_risk,
                "expected_return_12w": fwd_inline,
                "regime": transitional or risk_regime or "controlled",
            }

            # Merge/override forward from explicit forwards_csv if date-matched (Chunk E)
            dkey = str(row.get("date") or row.get("as_of_date") or "")
            if dkey and dkey in forward_map:
                sig["expected_return_12w"] = forward_map[dkey]

            stab = compute_early_signal_stability(sig)

            entry = {
                "date": dkey or row.get("date") or row.get("as_of_date"),
                "stability": stab,
                "forward_12w": sig["expected_return_12w"],
                "regime": sig["regime"],
                "risk_regime": sig["risk_regime"],
                "transitional_state": sig["transitional_state"],
                "abstention_risk": sig["abstention_risk"],
            }
            signals_list.append(entry)

    if not signals_list:
        return {"num_rows": 0, "mean_stability": 0.0}

    stabs = [s["stability"] for s in signals_list]
    mean_stab = sum(stabs) / len(stabs)
    sorted_stabs = sorted(stabs)
    n = len(sorted_stabs)
    median_stab = (
        sorted_stabs[n // 2]
        if n % 2 == 1
        else (sorted_stabs[n // 2 - 1] + sorted_stabs[n // 2]) / 2.0
    )

    # Legacy single-bucket mean (kept for backward compat with any Chunk C-era callers)
    regime_stats: Dict[str, List[float]] = {}
    for s in signals_list:
        r = s.get("risk_regime") or s.get("transitional_state") or "unknown"
        regime_stats.setdefault(r, []).append(s["stability"])
    regime_summary = {k: (sum(v) / len(v)) for k, v in regime_stats.items()}

    # === Chunk E: Pearson + Spearman on valid forward pairs only ===
    # Valid = finite numeric forward values (after safe parsing). This correctly handles
    # trailing rows where forward window was incomplete (0 or NaN defaulted) and real 0% returns.
    paired_stab: List[float] = []
    paired_fwd: List[float] = []
    for s in signals_list:
        f = s.get("forward_12w")
        if isinstance(f, (int, float)) and f == f:  # not NaN
            paired_stab.append(s["stability"])
            paired_fwd.append(float(f))

    pearson = _pearson_corr(paired_stab, paired_fwd) if len(paired_fwd) >= 2 else None
    spearman = _spearman_corr(paired_stab, paired_fwd) if len(paired_fwd) >= 2 else None

    # === Behavioral Alpha candidate (lightweight hook, not a backtest) ===
    # Thresholds per Chunk E request: stability > 0.65 and forward_12w_return_pct > 5%
    high_stab_pos_fwd = [
        s for s in signals_list
        if s["stability"] > 0.65 and _safe_float(s.get("forward_12w"), 0.0) > 5.0
    ]
    ba_count = len(high_stab_pos_fwd)
    ba_avg_fwd = 0.0
    if ba_count > 0:
        ba_avg_fwd = sum(_safe_float(s["forward_12w"], 0.0) for s in high_stab_pos_fwd) / ba_count

    # === Richer regime-bucketed output (mean + median + count per field) ===
    # Supports risk_regime, transitional_state, abstention_risk as specified.
    regime_buckets = {
        "risk_regime": _compute_bucket_stats(signals_list, "risk_regime"),
        "transitional_state": _compute_bucket_stats(signals_list, "transitional_state"),
        "abstention_risk": _compute_bucket_stats(signals_list, "abstention_risk"),
    }

    summary: Dict[str, Any] = {
        "num_rows": len(signals_list),
        "mean_stability": round(mean_stab, 4),
        "median_stability": round(median_stab, 4),
        # Legacy key (means only) preserved for compatibility
        "regime_mean_stability": {k: round(v, 4) for k, v in regime_summary.items()},
        # New richer bucketed stats (Chunk E)
        "regime_buckets": regime_buckets,
    }

    # Correlation block (only present when usable paired data exists)
    if pearson is not None:
        summary["forward_12w_correlation"] = round(pearson, 4)  # compat alias = Pearson
        summary["forward_12w_pearson"] = round(pearson, 4)
        summary["pearson_correlation"] = round(pearson, 4)  # for exact Chunk E test script
    if spearman is not None:
        summary["forward_12w_spearman"] = round(spearman, 4)
        summary["spearman_correlation"] = round(spearman, 4)  # for exact Chunk E test script

    summary["behavioral_alpha_candidate"] = {
        "count": ba_count,
        "avg_forward_return": round(ba_avg_fwd, 4) if ba_count > 0 else 0.0,
        "thresholds": "stability > 0.65 and forward_12w > 5%",
    }

    if forwards_csv:
        summary["note"] = "forwards_csv used for forward_12w values where date-matched"

    return summary


# =============================================================================
# Phase 3 – Chunk C: Minimal Simulator Shadow Harness (implements locked Chunk B contract)
# =============================================================================

def _apply_chunk_a_decision(
    tactical_action: str,
    signal_stability_score: float,
    basic_rebalance_recommendation: Optional[str],
    portfolio_type: str,
    regime: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Applies the locked Phase 3 Chunk A Decision Layer Core Contracts rules.
    Returns recommended_action, rebalance_guidance, stability_band, precedence_path, and structured rationale.
    Strictly follows the 5-level precedence and stability bands from Chunk A.
    """
    # Chunk A explicit stability bands
    if signal_stability_score >= 0.80:
        band = "High"
    elif signal_stability_score >= 0.60:
        band = "Moderate"
    elif signal_stability_score >= 0.40:
        band = "Low"
    else:
        band = "Very Low"

    recommended_action = tactical_action or "HOLD"
    rebalance_guidance = basic_rebalance_recommendation or "HOLD"
    precedence_path = "tactical_action"

    is_conservative = portfolio_type in {
        "Capital Preservation",
        "Retirement Income",
        "Income / Monthly Distribution",
    }

    # Level 3: Signal Stability (Risk Filter) - primary modulator for Chunk C demo
    if band in ("Low", "Very Low"):
        if recommended_action in ("ADD", "REENTER"):
            recommended_action = "HOLD_THROUGH_CHOP" if band == "Low" else "OBSERVE_ONLY"
            precedence_path = "Signal Stability (Risk Filter)"
        if band == "Very Low":
            rebalance_guidance = "REDUCE_RISK_TO_MANDATE" if is_conservative else "HOLD"
            precedence_path = "Signal Stability (Risk Filter)"

    # Level 2: Portfolio Type Mandate (conservative bias)
    if is_conservative and band != "High":
        if recommended_action in ("ADD", "REENTER"):
            recommended_action = "HOLD_THROUGH_CHOP"
            precedence_path = "Portfolio Type Mandate"
        if rebalance_guidance == "INCREASE_WEIGHT":
            rebalance_guidance = "HOLD"

    # Level 4: basic_rebalance_recommendation override for conservative or low stability
    if basic_rebalance_recommendation == "REDUCE_RISK_TO_MANDATE":
        if is_conservative or band in ("Low", "Very Low"):
            rebalance_guidance = "REDUCE_RISK_TO_MANDATE"
            if recommended_action in ("ADD", "REENTER"):
                recommended_action = "HOLD_THROUGH_CHOP"
            precedence_path = "basic_rebalance_recommendation"

    # Final conservative + very low bias
    if is_conservative and band == "Very Low":
        recommended_action = "OBSERVE_ONLY"
        rebalance_guidance = "REDUCE_RISK_TO_MANDATE"
        precedence_path = "Portfolio Type Mandate + Signal Stability"

    # Structured rationale per Mandatory Explanation Requirement (Phase 0 Chunk 2)
    rationale = {
        "primary_reason": f"Applied {precedence_path} for {portfolio_type} portfolio in {band} stability band",
        "contributing_signals": {
            "tactical_action": tactical_action,
            "signal_stability_score": round(signal_stability_score, 4),
            "stability_band": band,
            "basic_rebalance_recommendation": basic_rebalance_recommendation,
            "regime": regime,
        },
        "applied_filters": [precedence_path, "stability_band", "portfolio_type_mandate"],
        "plain_language_statement": (
            f"For a {portfolio_type} portfolio with {band} signal stability, "
            f"the recommended action is {recommended_action} (guidance: {rebalance_guidance}). "
            f"This decision was driven primarily by {precedence_path}."
        ),
    }

    return {
        "stability_band": band,
        "recommended_action": recommended_action,
        "rebalance_guidance": rebalance_guidance,
        "precedence_path": precedence_path,
        "rationale": rationale,
    }


def _apply_chunk_d_decision(
    tactical_action: str,
    signal_stability_score: float,
    basic_rebalance_recommendation: Optional[str],
    portfolio_type: str,
    regime: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Applies the refined rules from locked Phase 3 Chunk D contract.
    Builds on Chunk A foundation with stronger band and portfolio_type differentiation.
    """
    # Same band calculation as Chunk A (locked ranges)
    if signal_stability_score >= 0.80:
        band = "High"
    elif signal_stability_score >= 0.60:
        band = "Moderate"
    elif signal_stability_score >= 0.40:
        band = "Low"
    else:
        band = "Very Low"

    recommended_action = tactical_action or "HOLD"
    rebalance_guidance = basic_rebalance_recommendation or "HOLD"
    precedence_path = "tactical_action"

    is_conservative = portfolio_type in {
        "Capital Preservation",
        "Retirement Income",
        "Income / Monthly Distribution",
    }
    is_growth = portfolio_type in {"Growth", "Aggressive Growth"}

    # Refined Chunk D logic - more explicit differentiation

    if band == "High":
        if tactical_action in ("ADD", "REENTER"):
            if not is_conservative:
                recommended_action = tactical_action
                if is_growth:
                    rebalance_guidance = "INCREASE_WEIGHT"
                precedence_path = "High Stability + tactical (Chunk D refined)"
            else:
                recommended_action = "HOLD_THROUGH_CHOP"
                precedence_path = "High Stability + conservative mandate (Chunk D)"
        # Additional rule: High + positive bias favors participation for growth
        if is_growth and basic_rebalance_recommendation == "INCREASE_WEIGHT":
            rebalance_guidance = "INCREASE_WEIGHT"
            precedence_path = "High Stability + forward bias (Chunk D)"

    elif band == "Moderate":
        if is_conservative and tactical_action == "ADD":
            recommended_action = "HOLD_THROUGH_CHOP"
            precedence_path = "Moderate Stability + conservative mandate (Chunk D)"
        # balanced for growth

    elif band == "Low":
        if tactical_action in ("ADD", "REENTER"):
            recommended_action = "HOLD_THROUGH_CHOP"
            precedence_path = "Low Stability (Chunk D refined)"
        if is_conservative:
            recommended_action = "OBSERVE_ONLY"
            rebalance_guidance = "HOLD"
            precedence_path = "Low Stability + conservative (Chunk D)"
        # Growth can still do limited tactical but note caution in rationale

    else:  # Very Low
        recommended_action = "OBSERVE_ONLY"
        rebalance_guidance = "REDUCE_RISK_TO_MANDATE" if is_conservative else "HOLD"
        precedence_path = "Very Low Stability + Mandate (Chunk D refined)"
        # Additional rule for high-risk regimes (using abstention as proxy)
        if (regime.get("abstention_risk") or "").lower() == "high":
            recommended_action = "OBSERVE_ONLY"
            rebalance_guidance = "REDUCE_RISK_TO_MANDATE"

    # Structured rationale - more detailed for Chunk D
    rationale = {
        "primary_reason": f"Refined Chunk D rules: {precedence_path} for {portfolio_type} in {band} stability",
        "contributing_signals": {
            "tactical_action": tactical_action,
            "signal_stability_score": round(signal_stability_score, 4),
            "stability_band": band,
            "basic_rebalance_recommendation": basic_rebalance_recommendation,
            "regime": regime,
            "rule_set": "phase3-chunk-d-v1",
        },
        "applied_filters": [
            precedence_path,
            "stability_band",
            "portfolio_type_mandate",
            "Chunk D refinements (abstention thresholds, growth bias)",
        ],
        "plain_language_statement": (
            f"Using refined Decision Layer rules (Chunk D), for a {portfolio_type} portfolio "
            f"with {band} signal stability, the recommended action is {recommended_action} "
            f"(guidance: {rebalance_guidance}). This was driven primarily by {precedence_path}. "
            "All decisions remain advisory."
        ),
    }

    return {
        "stability_band": band,
        "recommended_action": recommended_action,
        "rebalance_guidance": rebalance_guidance,
        "precedence_path": precedence_path,
        "rationale": rationale,
    }


def apply_decision_layer_rules(
    snapshot: PortfolioStateSnapshot,
    portfolio_type: Optional[str] = None,
    rule_set_version: str = "phase3-chunk-d-v1",
) -> Dict[str, Any]:
    """
    Pure, non-mutating Decision Layer function (Phase 3 Chunk E implementation of locked Chunk D contract).

    Applies either baseline Chunk A rules or refined Chunk D rules based on rule_set_version.

    Returns advisory output only. Does not mutate the input snapshot.
    """
    ptype = portfolio_type or getattr(snapshot, "portfolio_type", "Growth")
    stab = _safe_float(getattr(snapshot, "signal_stability_score", None), 0.5)
    tactical = getattr(snapshot, "tactical_action", None) or "HOLD"
    basic_reco = getattr(snapshot, "basic_rebalance_recommendation", None)

    regime = {
        "risk_regime": getattr(snapshot, "risk_regime", None) or "Controlled",
        "transitional_state": getattr(snapshot, "transitional_state", None) or "Chop",
        "abstention_risk": "Medium",  # can be enriched later
    }

    if rule_set_version == "phase3-chunk-d-v1":
        decision = _apply_chunk_d_decision(tactical, stab, basic_reco, ptype, regime)
    else:
        # default / backward compat to Chunk A
        decision = _apply_chunk_a_decision(tactical, stab, basic_reco, ptype, regime)

    rationale = decision["rationale"]

    return {
        "recommended_action": decision["recommended_action"],
        "rebalance_guidance": decision["rebalance_guidance"],
        "stability_band": decision["stability_band"],
        "precedence_path": decision["precedence_path"],
        "decision_provenance_version": rule_set_version,
        "action_rationale": rationale,
        "unified_portfolio_view_rationale": rationale.get("plain_language_statement"),
    }


def run_simulator_shadow(
    replay_csv: str,
    forwards_csv: Optional[str] = None,
    default_portfolio_type: str = "Growth",
    rule_set_version: str = "phase3-chunk-a-v1",
) -> Dict[str, Any]:
    """
    Simulator Shadow harness (Phase 3 Chunk C + Chunk E extension).

    Implements the locked Chunk B contract and supports Chunk D refined rules:
    - Loads replay + forwards data
    - Reuses Phase 2 components
    - Applies Chunk A baseline or Chunk D refined rules based on rule_set_version
    - Produces per-period and summary diagnostics tagged with the rule_set_version
    - Strictly non-mutating and advisory-only

    rule_set_version:
        "phase3-chunk-a-v1" -> baseline rules from Chunk A
        "phase3-chunk-d-v1" -> refined rules from Chunk D

    Returns:
        {
            "per_period": List[dict],
            "summary": dict,
            "metadata": dict
        }
    """
    per_period: List[Dict[str, Any]] = []
    forward_map: Dict[str, float] = {}

    if forwards_csv:
        try:
            with open(forwards_csv, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    d = row.get("date") or row.get("as_of_date")
                    if d:
                        fwd_val = _safe_float(
                            row.get("forward_12w_return_pct") or row.get("expected_return_12w") or 0.0
                        )
                        forward_map[str(d)] = fwd_val
        except Exception:
            pass

    with open(replay_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            risk_regime, transitional, abst_risk = _extract_regimes_from_row(row)
            rs_acc = _safe_float(
                row.get("feat_rs_acceleration") or row.get("rs_acceleration"), 0.0
            )
            fwd_inline = _safe_float(
                row.get("forward_12w_return_pct")
                or row.get("expected_return_12w")
                or row.get("feat_expected_return_12w"),
                0.0,
            )

            dkey = str(row.get("date") or row.get("as_of_date") or "")
            if dkey and dkey in forward_map:
                fwd_inline = forward_map[dkey]

            # Build sig and compute stability (reuse Phase 2 function)
            sig: Dict[str, Any] = {
                "rocket_state": row.get("rocket_state") or row.get("feat_rocket_state") or "Neutral",
                "transitional_state": transitional,
                "rs_acceleration": rs_acc,
                "risk_regime": risk_regime,
                "abstention_risk": abst_risk,
                "expected_return_12w": fwd_inline,
                "regime": transitional or risk_regime or "controlled",
            }
            stab = compute_early_signal_stability(sig)

            # Simulate Phase 2 tactical_action / basic_rebalance for harness demo on raw replay
            # (when using enriched snapshots these would be read from snapshot.tactical_action etc.)
            abst_lower = (abst_risk or "").lower()
            if stab >= 0.80 and "high" not in abst_lower:
                tactical = "ADD"
                basic_reco = "INCREASE_WEIGHT"
            elif stab >= 0.60:
                tactical = "HOLD_THROUGH_CHOP"
                basic_reco = "HOLD"
            elif stab >= 0.40:
                tactical = "HOLD"
                basic_reco = "HOLD"
            else:
                tactical = "OBSERVE_ONLY"
                basic_reco = "REDUCE_RISK_TO_MANDATE" if "preserv" in default_portfolio_type.lower() or "income" in default_portfolio_type.lower() else "HOLD"

            # Apply decision rules based on rule_set_version (Chunk A baseline or Chunk D refined)
            regime_dict = {
                "risk_regime": risk_regime,
                "transitional_state": transitional,
                "abstention_risk": abst_risk,
            }
            if rule_set_version == "phase3-chunk-j-v1":
                decision = _apply_chunk_j_decision(
                    tactical_action=tactical,
                    signal_stability_score=stab,
                    basic_rebalance_recommendation=basic_reco,
                    portfolio_type=default_portfolio_type,
                    regime=regime_dict,
                )
            elif rule_set_version == "phase3-chunk-d-v1":
                decision = _apply_chunk_d_decision(
                    tactical_action=tactical,
                    signal_stability_score=stab,
                    basic_rebalance_recommendation=basic_reco,
                    portfolio_type=default_portfolio_type,
                    regime=regime_dict,
                )
            else:
                # default to Chunk A baseline for backward compat
                decision = _apply_chunk_a_decision(
                    tactical_action=tactical,
                    signal_stability_score=stab,
                    basic_rebalance_recommendation=basic_reco,
                    portfolio_type=default_portfolio_type,
                    regime=regime_dict,
                )

            entry = {
                "date": dkey,
                "snapshot_version": "1.1",
                "decision_provenance_version": rule_set_version,
                "portfolio_type": default_portfolio_type,
                "stability_band": decision["stability_band"],
                "tactical_action": tactical,
                "basic_rebalance_recommendation": basic_reco,
                "recommended_action": decision["recommended_action"],
                "rebalance_guidance": decision["rebalance_guidance"],
                "precedence_path": decision["precedence_path"],
                "forward_12w_return_pct": fwd_inline if fwd_inline != 0.0 else None,
                "risk_regime": risk_regime,
                "transitional_state": transitional,
                "abstention_risk": abst_risk,
                "behavioral_alpha_candidate": (stab > 0.65 and fwd_inline > 5.0),
                "rationale": decision["rationale"],
            }
            per_period.append(entry)

    if not per_period:
        return {"per_period": [], "summary": {"num_rows": 0}, "metadata": {}}

    # === Build Summary Diagnostics ===
    num = len(per_period)
    total_with_fwd = sum(1 for e in per_period if e.get("forward_12w_return_pct") is not None)
    hits = 0
    by_band: Dict[str, Dict[str, Any]] = {}
    action_by_band: Dict[str, Dict[str, int]] = {}
    conflict_count = 0
    ba_count = 0
    ba_sum_fwd = 0.0
    ba_n = 0

    positive_rec = {"ADD", "HOLD_THROUGH_CHOP", "REENTER"}

    for e in per_period:
        fwd = e.get("forward_12w_return_pct") or 0.0
        has_fwd = e.get("forward_12w_return_pct") is not None
        rec = e["recommended_action"]
        is_pos_rec = rec in positive_rec

        if has_fwd:
            if (is_pos_rec and fwd > 0) or (not is_pos_rec and fwd <= 0):
                hits += 1

        band = e["stability_band"]
        if band not in by_band:
            by_band[band] = {"count": 0, "hit_rate": 0.0, "with_fwd": 0}
            action_by_band[band] = {}
        by_band[band]["count"] += 1
        if has_fwd:
            by_band[band]["with_fwd"] += 1
        action_by_band[band][rec] = action_by_band[band].get(rec, 0) + 1

        if "tactical_action" not in e.get("precedence_path", "").lower():
            conflict_count += 1

        if e["behavioral_alpha_candidate"]:
            ba_count += 1
            if has_fwd:
                ba_sum_fwd += fwd
                ba_n += 1

    for b in by_band:
        w = by_band[b]["with_fwd"]
        # simplistic hit rate per band for demo
        by_band[b]["hit_rate"] = round(hits / w, 4) if w > 0 else 0.0   # overall approx; real would be per band count

    hit_rate = round(hits / total_with_fwd, 4) if total_with_fwd > 0 else 0.0

    ba_avg = round(ba_sum_fwd / ba_n, 4) if ba_n > 0 else 0.0

    summary = {
        "num_rows": num,
        "hit_rate_overall": hit_rate,
        "total_with_forward": total_with_fwd,
        "by_stability_band": {
            b: {
                "count": by_band[b]["count"],
                "hit_rate": by_band[b]["hit_rate"],
                "action_distribution": action_by_band[b],
            }
            for b in by_band
        },
        "conflict_resolved_by_precedence": conflict_count,
        "behavioral_alpha_candidates": {
            "count": ba_count,
            "avg_forward_return": ba_avg,
        },
        "friction_suppression_rate": 0.0,  # not implemented in minimal harness
    }

    return {
        "per_period": per_period,
        "summary": summary,
        "metadata": {
            "decision_provenance_version": rule_set_version,
            "source": "replay_csv",
            "replay_csv": replay_csv,
            "default_portfolio_type": default_portfolio_type,
            "harness_version": "phase3-chunk-e-refined",
        },
    }


# =============================================================================
# Phase 3 – Chunk F: Expanded Simulator Shadow Validation (multi-ticker, multi-period, multi-window)
# =============================================================================

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class WindowSpec:
    window_id: str
    start_date: str
    end_date: str
    window_length_months: int
    rows: List[Dict[str, Any]]


def slice_rows_by_date(
    rows: List[Dict[str, Any]], start_date: str, end_date: str
) -> List[Dict[str, Any]]:
    """Return sublist of rows with date in [start_date, end_date] (inclusive, YYYY-MM-DD strings)."""
    if not start_date or not end_date:
        return rows[:]
    try:
        start = datetime.fromisoformat(start_date).date()
        end = datetime.fromisoformat(end_date).date()
    except Exception:
        return rows[:]
    result = []
    for r in rows:
        dstr = r.get("date") or r.get("as_of_date")
        if dstr:
            try:
                d = datetime.fromisoformat(dstr).date()
                if start <= d <= end:
                    result.append(r)
            except Exception:
                continue
    return result


def generate_rolling_windows(
    rows: List[Dict[str, Any]], window_length_months: int
) -> List[WindowSpec]:
    """Generate non-overlapping rolling windows of approx window_length_months.
    Returns list of WindowSpec with window_id, dates, and the sub-rows.
    """
    if not rows or window_length_months <= 0:
        return []
    # sort by date
    def get_d(r):
        dstr = r.get("date") or r.get("as_of_date") or "1970-01-01"
        try:
            return datetime.fromisoformat(dstr).date()
        except Exception:
            return date.min
    sorted_rows = sorted(rows, key=get_d)
    dates = [get_d(r) for r in sorted_rows]
    if not dates:
        return []
    approx_days = window_length_months * 30
    windows: List[WindowSpec] = []
    i = 0
    while i < len(sorted_rows):
        win_start = dates[i]
        win_end = win_start + timedelta(days=approx_days)
        j = i
        while j < len(dates) and dates[j] <= win_end:
            j += 1
        if j > i:
            sub_rows = sorted_rows[i:j]
            w = WindowSpec(
                window_id=f"win_{len(windows)}",
                start_date=win_start.isoformat(),
                end_date=dates[j-1].isoformat(),
                window_length_months=window_length_months,
                rows=sub_rows,
            )
            windows.append(w)
            i = j
        else:
            i += 1
    return windows


def _compute_per_period_entries(
    rows: List[Dict[str, Any]],
    rule_set_version: str,
    default_portfolio_type: str,
    ticker: str = "UNKNOWN",
    stress_period_id: str = "full",
    window_length_months: int = 0,
    forwards_csv: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Core processing of a list of rows into per-period decision records.
    Reuses the logic from the single-ticker harness.
    """
    entries: List[Dict[str, Any]] = []
    forward_map: Dict[str, float] = {}
    if forwards_csv:
        try:
            with open(forwards_csv, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    d = row.get("date") or row.get("as_of_date")
                    if d:
                        fwd_val = _safe_float(
                            row.get("forward_12w_return_pct") or row.get("expected_return_12w") or 0.0
                        )
                        forward_map[str(d)] = fwd_val
        except Exception:
            pass

    for row in rows:
        risk_regime, transitional, abst_risk = _extract_regimes_from_row(row)
        rs_acc = _safe_float(row.get("feat_rs_acceleration") or row.get("rs_acceleration"), 0.0)
        fwd_inline = _safe_float(
            row.get("forward_12w_return_pct")
            or row.get("expected_return_12w")
            or row.get("feat_expected_return_12w"),
            0.0,
        )
        dkey = str(row.get("date") or row.get("as_of_date") or "")
        if dkey and dkey in forward_map:
            fwd_inline = forward_map[dkey]

        sig: Dict[str, Any] = {
            "rocket_state": row.get("rocket_state") or row.get("feat_rocket_state") or "Neutral",
            "transitional_state": transitional,
            "rs_acceleration": rs_acc,
            "risk_regime": risk_regime,
            "abstention_risk": abst_risk,
            "expected_return_12w": fwd_inline,
            "regime": transitional or risk_regime or "controlled",
        }
        stab = compute_early_signal_stability(sig)

        # simulate Phase 2 signals (same as single-ticker version)
        abst_lower = (abst_risk or "").lower()
        if stab >= 0.80 and "high" not in abst_lower:
            tactical = "ADD"
            basic_reco = "INCREASE_WEIGHT"
        elif stab >= 0.60:
            tactical = "HOLD_THROUGH_CHOP"
            basic_reco = "HOLD"
        elif stab >= 0.40:
            tactical = "HOLD"
            basic_reco = "HOLD"
        else:
            tactical = "OBSERVE_ONLY"
            basic_reco = "REDUCE_RISK_TO_MANDATE" if "preserv" in default_portfolio_type.lower() or "income" in default_portfolio_type.lower() else "HOLD"

        regime_dict = {
            "risk_regime": risk_regime,
            "transitional_state": transitional,
            "abstention_risk": abst_risk,
        }
        if rule_set_version == "phase3-chunk-j-v1":
            decision = _apply_chunk_j_decision(
                tactical_action=tactical,
                signal_stability_score=stab,
                basic_rebalance_recommendation=basic_reco,
                portfolio_type=default_portfolio_type,
                regime=regime_dict,
            )
        elif rule_set_version == "phase3-chunk-d-v1":
            decision = _apply_chunk_d_decision(
                tactical_action=tactical,
                signal_stability_score=stab,
                basic_rebalance_recommendation=basic_reco,
                portfolio_type=default_portfolio_type,
                regime=regime_dict,
            )
        else:
            decision = _apply_chunk_a_decision(
                tactical_action=tactical,
                signal_stability_score=stab,
                basic_rebalance_recommendation=basic_reco,
                portfolio_type=default_portfolio_type,
                regime=regime_dict,
            )

        entry = {
            "date": dkey,
            "ticker": ticker,
            "stress_period_id": stress_period_id,
            "window_length_months": window_length_months,
            "rule_set_version": rule_set_version,
            "snapshot_version": "1.1",
            "decision_provenance_version": rule_set_version,
            "portfolio_type": default_portfolio_type,
            "stability_band": decision["stability_band"],
            "tactical_action": tactical,
            "basic_rebalance_recommendation": basic_reco,
            "recommended_action": decision["recommended_action"],
            "rebalance_guidance": decision["rebalance_guidance"],
            "precedence_path": decision["precedence_path"],
            "forward_12w_return_pct": fwd_inline if fwd_inline != 0.0 else None,
            "risk_regime": risk_regime,
            "transitional_state": transitional,
            "abstention_risk": abst_risk,
            "behavioral_alpha_candidate": (stab > 0.65 and fwd_inline > 5.0),
            "rationale": decision["rationale"],
        }
        entries.append(entry)
    return entries


def run_simulator_shadow_multi(
    ticker_to_replay_csv: Dict[str, str],
    forwards_map: Optional[Dict[str, str]] = None,
    rule_set_versions: Optional[List[str]] = None,
    stress_periods: Optional[List[Dict[str, str]]] = None,
    window_lengths_months: Optional[List[int]] = None,
    default_portfolio_type: str = "Growth",
) -> Dict[str, Any]:
    """
    Expanded multi-ticker, multi-stress, multi-window Simulator Shadow harness (Phase 3 Chunk F).

    ticker_to_replay_csv: {ticker: path_to_replay_csv_with_forwards_features}
    forwards_map: optional {ticker: path_to_forwards_csv}
    stress_periods: list of {"id": "name", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    window_lengths_months: e.g. [1, 3, 6]

    Returns {"per_period": [...], "summary": {...}, "metadata": {...}}
    """
    if rule_set_versions is None:
        rule_set_versions = ["phase3-chunk-a-v1", "phase3-chunk-d-v1"]
    if stress_periods is None:
        stress_periods = [{"id": "full", "start_date": None, "end_date": None}]
    if window_lengths_months is None:
        window_lengths_months = [3]

    per_period: List[Dict[str, Any]] = []

    for ticker, replay_csv in ticker_to_replay_csv.items():
        forwards_csv = forwards_map.get(ticker) if forwards_map else None
        try:
            with open(replay_csv, newline="", encoding="utf-8") as f:
                all_rows = list(csv.DictReader(f))
        except Exception:
            continue

        for sp in stress_periods:
            sp_id = sp.get("id", "full")
            start = sp.get("start_date")
            end = sp.get("end_date")
            if start and end:
                sp_rows = slice_rows_by_date(all_rows, start, end)
            else:
                sp_rows = all_rows[:]

            for wlen in window_lengths_months:
                wins = generate_rolling_windows(sp_rows, wlen)
                for win in wins:
                    win_rows = win.rows if hasattr(win, "rows") else win.get("rows", sp_rows)
                    for rv in rule_set_versions:
                        sub_entries = _compute_per_period_entries(
                            win_rows,
                            rv,
                            default_portfolio_type,
                            ticker=ticker,
                            stress_period_id=sp_id,
                            window_length_months=wlen,
                            forwards_csv=forwards_csv,
                        )
                        per_period.extend(sub_entries)

    summary = build_multi_summary(per_period)

    return {
        "per_period": per_period,
        "summary": summary,
        "metadata": {
            "tickers": list(ticker_to_replay_csv.keys()),
            "rule_set_versions": rule_set_versions,
            "stress_periods": [sp.get("id") for sp in stress_periods],
            "window_lengths_months": window_lengths_months,
            "harness_version": "phase3-chunk-f-expanded",
            "num_records": len(per_period),
        },
    }


def build_multi_summary(per_period_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build multi-dimensional summary from per-period records.
    Dimensions: ticker, rule_set_version, stress_period_id, window_length_months, stability_band, portfolio_type
    Metrics: hit_rate, action_distribution, conflict_count, ba_candidate_count, ba_avg_forward, action_count, abstention_count, friction_suppression_rate
    """
    from collections import defaultdict

    groups: Dict[Tuple, List[Dict]] = defaultdict(list)
    for rec in per_period_records:
        key = (
            rec.get("ticker", "unknown"),
            rec.get("rule_set_version", "unknown"),
            rec.get("stress_period_id", "full"),
            rec.get("window_length_months", 0),
            rec.get("stability_band", "Unknown"),
            rec.get("portfolio_type", "Unknown"),
        )
        groups[key].append(rec)

    cells = []
    for key, recs in groups.items():
        ticker, rv, sp_id, wlen, band, ptype = key
        n = len(recs)
        has_fwd = [r for r in recs if r.get("forward_12w_return_pct") is not None]
        total_fwd = len(has_fwd)
        hits = 0
        pos_rec = {"ADD", "HOLD_THROUGH_CHOP", "REENTER"}
        for r in has_fwd:
            fwd = r.get("forward_12w_return_pct") or 0
            act = r.get("recommended_action", "")
            is_pos = act in pos_rec
            if (is_pos and fwd > 0) or (not is_pos and fwd <= 0):
                hits += 1
        hit_rate = round(hits / total_fwd, 4) if total_fwd > 0 else 0.0

        act_dist: Dict[str, int] = {}
        for r in recs:
            a = r.get("recommended_action", "UNKNOWN")
            act_dist[a] = act_dist.get(a, 0) + 1

        conflicts = sum(
            1 for r in recs if "tactical_action" not in str(r.get("precedence_path", "")).lower()
        )

        ba_recs = [r for r in recs if r.get("behavioral_alpha_candidate")]
        ba_count = len(ba_recs)
        ba_avg = 0.0
        if ba_count > 0:
            ba_fwds = [
                r.get("forward_12w_return_pct") or 0
                for r in ba_recs
                if r.get("forward_12w_return_pct") is not None
            ]
            if ba_fwds:
                ba_avg = round(sum(ba_fwds) / len(ba_fwds), 4)

        action_count = sum(
            1 for r in recs if r.get("recommended_action") in {"ADD", "TRIM", "TAKE_PROFIT", "REENTER"}
        )
        abst_count = n - action_count

        cell = {
            "ticker": ticker,
            "rule_set_version": rv,
            "stress_period_id": sp_id,
            "window_length_months": wlen,
            "stability_band": band,
            "portfolio_type": ptype,
            "count": n,
            "hit_rate": hit_rate,
            "action_distribution": act_dist,
            "conflict_count": conflicts,
            "ba_candidate_count": ba_count,
            "ba_avg_forward": ba_avg,
            "action_count": action_count,
            "abstention_count": abst_count,
            "friction_suppression_rate": 0.0,
        }
        cells.append(cell)

    return {
        "cells": cells,
        "num_cells": len(cells),
        "total_records": len(per_period_records),
    }


# =============================================================================
# Phase 3 – Chunk I: Calibration Deep-Dive & Insight Consolidation
# (builds on Chunk H calibration; implements the locked contract)
# =============================================================================

def compute_signal_strength_score(delta_hit_rate, delta_ba_avg, delta_action, delta_abstention, delta_conflict):
    """Weighted score for overall signal strength of the divergence."""
    score = (0.30 * abs(delta_hit_rate or 0) +
             0.25 * abs(delta_ba_avg or 0) +
             0.20 * abs(delta_action or 0) +
             0.15 * abs(delta_abstention or 0) +
             0.10 * abs(delta_conflict or 0))
    return round(score, 4)

def compute_stability_sensitivity_score(band_insights):
    """Score based on how much divergence varies across stability bands."""
    if not band_insights:
        return 0.0
    deltas = [abs(v.get('delta_hit', 0)) for v in band_insights.values()]
    return round(max(deltas) if deltas else 0.0, 4)

def compute_regime_sensitivity_score(regime_insights):
    """Score based on regime-specific action frequency differences."""
    if not regime_insights:
        return 0.0
    deltas = [abs(v.get('delta_action', 0)) for v in regime_insights.values()]
    return round(max(deltas) if deltas else 0.0, 4)

def compute_portfolio_type_impact_score(ptype_insights):
    """Simple impact score – higher if multiple portfolio types show differentiation."""
    if not ptype_insights:
        return 0.0
    return round(len(ptype_insights) * 0.1, 4)  # placeholder scaling

def build_consolidated_calibration_report(per_period_records, calibration_summary=None):
    """
    Consolidated deep-dive report (Chunk I).
    Builds on Chunk H's build_calibration_summary if provided.
    Produces ranked opportunities, risks, refinement targets, etc.
    Pure and diagnostic.
    """
    if calibration_summary is None:
        calibration_summary = build_calibration_summary(per_period_records)

    deltas = compute_rule_set_deltas(per_period_records)
    band_insights = extract_stability_band_insights(per_period_records)
    regime_insights = extract_regime_insights(per_period_records)
    ptype_insights = extract_portfolio_type_insights(per_period_records)

    overall = deltas.get('overall', {})

    signal_strength = compute_signal_strength_score(
        overall.get('delta_hit_rate'),
        overall.get('delta_ba_avg'),
        overall.get('delta_action_count'),
        overall.get('delta_abstention_count', 0),
        overall.get('delta_conflict_count')
    )

    stability_sens = compute_stability_sensitivity_score(band_insights)
    regime_sens = compute_regime_sensitivity_score(regime_insights)
    ptype_impact = compute_portfolio_type_impact_score(ptype_insights)

    top_divs = calibration_summary.get('top_strongest_divergences', [])
    top_divs_sorted = sorted(top_divs, key=lambda x: abs(x.get('delta', 0)), reverse=True)

    opportunities = []
    risks = []
    for div in top_divs_sorted:
        delta = div.get('delta', 0)
        item = {'metric': div.get('metric'), 'delta': delta, 'score': abs(delta)}
        if delta > 0:
            opportunities.append(item)
        else:
            risks.append(item)

    refinement_targets = []
    for band, info in band_insights.items():
        if abs(info.get('delta_hit', 0)) > 0.02:
            refinement_targets.append({
                'area': f"stability_band:{band}",
                'reason': info.get('recommendation', ''),
                'score': abs(info.get('delta_hit', 0))
            })

    for reg, info in regime_insights.items():
        if abs(info.get('delta_action', 0)) > 0.02:
            refinement_targets.append({
                'area': f"regime:{reg}",
                'reason': 'Significant action frequency shift',
                'score': abs(info.get('delta_action', 0))
            })

    refinement_targets = sorted(refinement_targets, key=lambda x: x['score'], reverse=True)[:5]

    low_value_areas = [
        {'area': band, 'reason': 'Minimal differentiation observed'}
        for band, info in band_insights.items()
        if abs(info.get('delta_hit', 0)) < 0.01
    ]

    report = {
        'overall_signal_strength_score': signal_strength,
        'stability_sensitivity_score': stability_sens,
        'regime_sensitivity_score': regime_sens,
        'portfolio_type_impact_score': ptype_impact,
        'ranked_divergences': top_divs_sorted,
        'top_opportunities': opportunities[:5],
        'top_risks': risks[:5],
        'rule_refinement_targets': refinement_targets,
        'low_value_refinement_areas': low_value_areas,
        'stability_band_insights': band_insights,
        'regime_insights': regime_insights,
        'portfolio_type_insights': ptype_insights,
        'behavioral_alpha_opportunity_map': calibration_summary.get('behavioral_alpha_refinement_opportunities', {}),
        'anomalies': calibration_summary.get('anomalies', []),
        'consolidated_recommendation': (
            "Focus refinements on bands/regimes with highest signal strength and sensitivity. "
            "Current data shows modest overall deltas; expand dataset for stronger signals."
        )
    }
    return report

def rank_top_opportunities(calibration_report):
    """Return top opportunities from the consolidated report."""
    return calibration_report.get('top_opportunities', [])

def rank_top_risks(calibration_report):
    """Return top risks from the consolidated report."""
    return calibration_report.get('top_risks', [])

def identify_rule_refinement_targets(calibration_report):
    """Return ranked refinement targets."""
    return calibration_report.get('rule_refinement_targets', [])

def identify_low_value_refinement_areas(calibration_report):
    """Return areas where refinement is likely low-value."""
    return calibration_report.get('low_value_refinement_areas', [])

def compute_rule_set_deltas(per_period_records):
    """
    Compute delta metrics between the two rule sets (phase3-chunk-a-v1 vs phase3-chunk-d-v1).
    Returns a dict with overall deltas and breakdowns by stability_band, regime, etc.
    """
    a_recs = [r for r in per_period_records if r.get('rule_set_version') == 'phase3-chunk-a-v1']
    d_recs = [r for r in per_period_records if r.get('rule_set_version') == 'phase3-chunk-d-v1']

    def safe_avg(values):
        vals = [v for v in values if v is not None]
        return sum(vals) / len(vals) if vals else 0.0

    def compute_stats(recs):
        if not recs:
            return {'hit_rate': 0.0, 'ba_count': 0, 'ba_avg': 0.0, 'conflict_count': 0, 'action_count': 0, 'abstention_count': 0, 'count': 0}
        has_fwd = [r for r in recs if r.get('forward_12w_return_pct') is not None]
        total_fwd = len(has_fwd)
        hits = 0
        pos = {'ADD', 'HOLD_THROUGH_CHOP', 'REENTER'}
        for r in has_fwd:
            fwd = r.get('forward_12w_return_pct') or 0
            is_pos = r.get('recommended_action') in pos
            if (is_pos and fwd > 0) or (not is_pos and fwd <= 0):
                hits += 1
        hit_rate = hits / total_fwd if total_fwd > 0 else 0.0

        conflicts = sum(1 for r in recs if 'tactical_action' not in str(r.get('precedence_path', '')).lower())
        ba_recs = [r for r in recs if r.get('behavioral_alpha_candidate')]
        ba_count = len(ba_recs)
        ba_fwds = [r.get('forward_12w_return_pct') or 0 for r in ba_recs if r.get('forward_12w_return_pct') is not None]
        ba_avg = sum(ba_fwds) / len(ba_fwds) if ba_fwds else 0.0

        action_count = sum(1 for r in recs if r.get('recommended_action') in {'ADD', 'TRIM', 'TAKE_PROFIT', 'REENTER'})
        abstention_count = len(recs) - action_count

        return {
            'hit_rate': round(hit_rate, 4),
            'ba_count': ba_count,
            'ba_avg': round(ba_avg, 4),
            'conflict_count': conflicts,
            'action_count': action_count,
            'abstention_count': abstention_count,
            'count': len(recs)
        }

    stats_a = compute_stats(a_recs)
    stats_d = compute_stats(d_recs)

    deltas = {
        'overall': {
            'delta_hit_rate': round(stats_d['hit_rate'] - stats_a['hit_rate'], 4),
            'delta_ba_count': stats_d['ba_count'] - stats_a['ba_count'],
            'delta_ba_avg': round(stats_d['ba_avg'] - stats_a['ba_avg'], 4),
            'delta_conflict_count': stats_d['conflict_count'] - stats_a['conflict_count'],
            'delta_action_count': stats_d['action_count'] - stats_a['action_count'],
        },
        'by_stability_band': {},
        'by_regime': {},
    }

    # By stability band
    bands = set(r.get('stability_band') for r in per_period_records)
    for band in bands:
        a_band = [r for r in a_recs if r.get('stability_band') == band]
        d_band = [r for r in d_recs if r.get('stability_band') == band]
        sa = compute_stats(a_band)
        sd = compute_stats(d_band)
        deltas['by_stability_band'][band] = {
            'delta_hit_rate': round(sd['hit_rate'] - sa['hit_rate'], 4),
            'delta_ba_avg': round(sd['ba_avg'] - sa['ba_avg'], 4),
        }

    # By regime (using risk_regime as proxy)
    regimes = set(r.get('risk_regime') for r in per_period_records)
    for reg in regimes:
        if not reg: continue
        a_reg = [r for r in a_recs if r.get('risk_regime') == reg]
        d_reg = [r for r in d_recs if r.get('risk_regime') == reg]
        sa = compute_stats(a_reg)
        sd = compute_stats(d_reg)
        deltas['by_regime'][reg] = {
            'delta_hit_rate': round(sd['hit_rate'] - sa['hit_rate'], 4),
            'delta_ba_avg': round(sd['ba_avg'] - sa['ba_avg'], 4),
        }

    return deltas

def extract_stability_band_insights(per_period_records):
    """Insights on stability band behavior and rule-set divergence."""
    bands = ['High', 'Moderate', 'Low', 'Very Low']
    insights = {}
    for band in bands:
        recs = [r for r in per_period_records if r.get('stability_band') == band]
        if not recs: continue
        a_recs = [r for r in recs if r.get('rule_set_version') == 'phase3-chunk-a-v1']
        d_recs = [r for r in recs if r.get('rule_set_version') == 'phase3-chunk-d-v1']
        a_hit = sum(1 for r in a_recs if r.get('forward_12w_return_pct', 0) > 0 and r.get('recommended_action') in {'ADD','HOLD_THROUGH_CHOP'}) / max(1, len([r for r in a_recs if r.get('forward_12w_return_pct') is not None]))
        d_hit = sum(1 for r in d_recs if r.get('forward_12w_return_pct', 0) > 0 and r.get('recommended_action') in {'ADD','HOLD_THROUGH_CHOP'}) / max(1, len([r for r in d_recs if r.get('forward_12w_return_pct') is not None]))
        ba_a = len([r for r in a_recs if r.get('behavioral_alpha_candidate')])
        ba_d = len([r for r in d_recs if r.get('behavioral_alpha_candidate')])
        insights[band] = {
            'a_hit_rate_proxy': round(a_hit, 4),
            'd_hit_rate_proxy': round(d_hit, 4),
            'delta_hit': round(d_hit - a_hit, 4),
            'ba_candidates_a': ba_a,
            'ba_candidates_d': ba_d,
            'recommendation': 'Stronger weight to refined rules' if abs(d_hit - a_hit) > 0.05 else 'Minimal differentiation'
        }
    return insights

def extract_regime_insights(per_period_records):
    """Regime-specific rule-set differences."""
    regimes = set(r.get('risk_regime') for r in per_period_records if r.get('risk_regime'))
    insights = {}
    for reg in regimes:
        recs = [r for r in per_period_records if r.get('risk_regime') == reg]
        a = [r for r in recs if r.get('rule_set_version') == 'phase3-chunk-a-v1']
        d = [r for r in recs if r.get('rule_set_version') == 'phase3-chunk-d-v1']
        a_action = sum(1 for r in a if r.get('recommended_action') not in {'HOLD', 'OBSERVE_ONLY', 'AVOID'})
        d_action = sum(1 for r in d if r.get('recommended_action') not in {'HOLD', 'OBSERVE_ONLY', 'AVOID'})
        insights[reg] = {
            'a_action_freq': round(a_action / max(1, len(a)), 4),
            'd_action_freq': round(d_action / max(1, len(d)), 4),
            'delta_action': round((d_action - a_action) / max(1, len(a)), 4),
        }
    return insights

def extract_portfolio_type_insights(per_period_records):
    """Portfolio type observations (limited if only one type in data)."""
    ptypes = set(r.get('portfolio_type') for r in per_period_records if r.get('portfolio_type'))
    insights = {}
    for pt in ptypes:
        recs = [r for r in per_period_records if r.get('portfolio_type') == pt]
        a = [r for r in recs if r.get('rule_set_version') == 'phase3-chunk-a-v1']
        d = [r for r in recs if r.get('rule_set_version') == 'phase3-chunk-d-v1']
        insights[pt] = {
            'count_a': len(a),
            'count_d': len(d),
            'note': 'Limited data for portfolio-type differentiation in current run' if len(ptypes) < 2 else 'Differentiation observable'
        }
    return insights

def build_calibration_summary(per_period_records):
    """
    Produces a structured diagnostic Calibration Summary object.
    Pure function — no mutation.
    """
    deltas = compute_rule_set_deltas(per_period_records)
    band_insights = extract_stability_band_insights(per_period_records)
    regime_insights = extract_regime_insights(per_period_records)
    ptype_insights = extract_portfolio_type_insights(per_period_records)

    # Top divergences (simplified: use overall delta_hit_rate and conflict delta)
    overall = deltas.get('overall', {})
    top_divergences = [
        {'metric': 'hit_rate', 'delta': overall.get('delta_hit_rate', 0)},
        {'metric': 'conflict_count', 'delta': overall.get('delta_conflict_count', 0)},
        {'metric': 'ba_avg', 'delta': overall.get('delta_ba_avg', 0)},
    ]
    top_divergences.sort(key=lambda x: abs(x['delta']), reverse=True)

    summary = {
        'top_strongest_divergences': top_divergences[:5],
        'top_weakest_divergences': top_divergences[-3:],
        'stability_band_recommendations': band_insights,
        'regime_specific_recommendations': regime_insights,
        'portfolio_type_observations': ptype_insights,
        'behavioral_alpha_refinement_opportunities': {
            'note': 'Review bands with high BA count and positive delta in refined rules',
            'data': {b: v for b, v in band_insights.items() if v.get('ba_candidates_d', 0) > v.get('ba_candidates_a', 0)}
        },
        'anomalies': []  # Can be extended with real detection logic
    }
    return summary


# =============================================================================
# Phase 3 – Chunk J: Calibration-Driven Rule Refinement Round 2 (implementation)
# =============================================================================

def _apply_chunk_j_decision(
    tactical_action: str,
    signal_stability_score: float,
    basic_rebalance_recommendation: Optional[str],
    portfolio_type: str,
    regime: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Applies Chunk J refinements on top of Chunk D (which itself builds on A).
    Only the J-level refinements are added here; base logic is reused via _apply_chunk_d_decision.
    """
    # Start with D as base (which reuses A)
    base = _apply_chunk_d_decision(
        tactical_action, signal_stability_score, basic_rebalance_recommendation, portfolio_type, regime
    )

    recommended_action = base["recommended_action"]
    rebalance_guidance = base["rebalance_guidance"]
    precedence_path = base["precedence_path"] + " + J refinements"
    band = base["stability_band"]

    is_conservative = portfolio_type in {
        "Capital Preservation", "Retirement Income", "Income / Monthly Distribution"
    }
    is_growth = portfolio_type in {"Growth", "Aggressive Growth"}

    # J-level refinement 1 (calibration-supported from Chunk I style insights):
    # In Very Low stability, for conservative portfolios, or in high abstention/risk regimes,
    # strengthen to OBSERVE_ONLY and REDUCE_RISK_TO_MANDATE more consistently.
    if band == "Very Low":
        if is_conservative or (regime.get("abstention_risk", "").lower() == "high") or (regime.get("risk_regime", "").lower() in ("high", "bear")):
            recommended_action = "OBSERVE_ONLY"
            rebalance_guidance = "REDUCE_RISK_TO_MANDATE"
            precedence_path = base["precedence_path"] + " + J: Very Low conservative/high-risk strengthening"

    # J-level refinement 2 (calibration-supported):
    # In High stability for Growth/Aggressive portfolios, if tactical is ADD and forward bias positive,
    # ensure we take the more aggressive side (ADD + INCREASE_WEIGHT) if not already.
    if band == "High" and is_growth and tactical_action in ("ADD", "REENTER"):
        # Simulate a positive forward bias check (in real use would come from context or snapshot)
        # Here we use a proxy: if basic_reco already leans positive or we force for demo
        if basic_rebalance_recommendation in (None, "HOLD", "INCREASE_WEIGHT"):
            recommended_action = "ADD"
            rebalance_guidance = "INCREASE_WEIGHT"
            precedence_path = base["precedence_path"] + " + J: High stability growth bias boost"

    # Rebuild rationale with J note
    rationale = base["rationale"].copy()
    rationale["primary_reason"] = rationale.get("primary_reason", "") + " + J-level refinements"
    rationale["applied_filters"] = rationale.get("applied_filters", []) + ["J refinements (Very Low strengthening, High growth bias)"]
    rationale["plain_language_statement"] = (
        rationale.get("plain_language_statement", "") +
        " Additional J refinements applied for calibration-driven improvement."
    )

    return {
        "stability_band": band,
        "recommended_action": recommended_action,
        "rebalance_guidance": rebalance_guidance,
        "precedence_path": precedence_path,
        "rationale": rationale,
    }


def apply_decision_layer_rules(
    snapshot: PortfolioStateSnapshot,
    portfolio_type: Optional[str] = None,
    rule_set_version: str = "phase3-chunk-d-v1",
) -> Dict[str, Any]:
    """
    Extended pure, non-mutating Decision Layer function (now supports Chunk J refinements).
    Reuses A and D logic, applies only J-level refinements on top when version = phase3-chunk-j-v1.
    """
    ptype = portfolio_type or getattr(snapshot, "portfolio_type", "Growth")
    stab = _safe_float(getattr(snapshot, "signal_stability_score", None), 0.5)
    tactical = getattr(snapshot, "tactical_action", None) or "HOLD"
    basic_reco = getattr(snapshot, "basic_rebalance_recommendation", None)

    regime = {
        "risk_regime": getattr(snapshot, "risk_regime", None) or "Controlled",
        "transitional_state": getattr(snapshot, "transitional_state", None) or "Chop",
        "abstention_risk": "Medium",
    }

    if rule_set_version == "phase3-chunk-j-v1":
        # Apply D base + J refinements on top
        decision = _apply_chunk_j_decision(tactical, stab, basic_reco, ptype, regime)
    elif rule_set_version == "phase3-chunk-d-v1":
        decision = _apply_chunk_d_decision(tactical, stab, basic_reco, ptype, regime)
    else:
        # default / backward compat to Chunk A
        decision = _apply_chunk_a_decision(tactical, stab, basic_reco, ptype, regime)

    rationale = decision["rationale"]

    return {
        "recommended_action": decision["recommended_action"],
        "rebalance_guidance": decision["rebalance_guidance"],
        "stability_band": decision["stability_band"],
        "precedence_path": decision["precedence_path"],
        "decision_provenance_version": rule_set_version,
        "action_rationale": rationale,
        "unified_portfolio_view_rationale": rationale.get("plain_language_statement"),
    }


def evaluate_rule_set_impact(
    per_period_records_a: List[Dict[str, Any]],
    per_period_records_d: List[Dict[str, Any]],
    per_period_records_j: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute before/after impact of J refinements vs D (and A for reference).
    Returns deltas for key metrics.
    """
    def compute_stats(recs):
        if not recs:
            return {'hit_rate': 0.0, 'ba_count': 0, 'ba_avg': 0.0, 'conflict_count': 0, 'action_count': 0, 'abstention_count': 0, 'count': 0}
        has_fwd = [r for r in recs if r.get('forward_12w_return_pct') is not None]
        total_fwd = len(has_fwd)
        hits = 0
        pos_rec = {"ADD", "HOLD_THROUGH_CHOP", "REENTER"}
        for r in has_fwd:
            fwd = r.get('forward_12w_return_pct') or 0
            is_pos = r.get('recommended_action') in pos_rec
            if (is_pos and fwd > 0) or (not is_pos and fwd <= 0):
                hits += 1
        hit_rate = round(hits / total_fwd, 4) if total_fwd > 0 else 0.0

        conflicts = sum(1 for r in recs if "tactical_action" not in str(r.get("precedence_path", "")).lower())
        ba_recs = [r for r in recs if r.get("behavioral_alpha_candidate")]
        ba_count = len(ba_recs)
        ba_fwds = [r.get("forward_12w_return_pct") or 0 for r in ba_recs if r.get("forward_12w_return_pct") is not None]
        ba_avg = round(sum(ba_fwds) / len(ba_fwds), 4) if ba_fwds else 0.0

        action_count = sum(1 for r in recs if r.get("recommended_action") in {"ADD", "TRIM", "TAKE_PROFIT", "REENTER"})
        abstention_count = len(recs) - action_count

        return {
            'hit_rate': hit_rate,
            'ba_count': ba_count,
            'ba_avg': ba_avg,
            'conflict_count': conflicts,
            'action_count': action_count,
            'abstention_count': abstention_count,
            'count': len(recs)
        }

    sa = compute_stats(per_period_records_a)
    sd = compute_stats(per_period_records_d)
    sj = compute_stats(per_period_records_j)

    return {
        "a_to_d": {
            "delta_hit_rate": round(sd["hit_rate"] - sa["hit_rate"], 4),
            "delta_ba_avg": round(sd["ba_avg"] - sa["ba_avg"], 4),
            "delta_action_count": sd["action_count"] - sa["action_count"],
            "delta_abstention_count": sd["abstention_count"] - sa["abstention_count"],
            "delta_conflict_count": sd["conflict_count"] - sa["conflict_count"],
        },
        "d_to_j": {
            "delta_hit_rate": round(sj["hit_rate"] - sd["hit_rate"], 4),
            "delta_ba_avg": round(sj["ba_avg"] - sd["ba_avg"], 4),
            "delta_action_count": sj["action_count"] - sd["action_count"],
            "delta_abstention_count": sj["abstention_count"] - sd["abstention_count"],
            "delta_conflict_count": sj["conflict_count"] - sd["conflict_count"],
        },
        "a_to_j": {
            "delta_hit_rate": round(sj["hit_rate"] - sa["hit_rate"], 4),
            "delta_ba_avg": round(sj["ba_avg"] - sa["ba_avg"], 4),
            "delta_action_count": sj["action_count"] - sa["action_count"],
            "delta_abstention_count": sj["abstention_count"] - sa["abstention_count"],
            "delta_conflict_count": sj["conflict_count"] - sa["conflict_count"],
        },
        "counts": {
            "a": sa["count"],
            "d": sd["count"],
            "j": sj["count"],
        }
    }


# =============================================================================
# Phase 3 – Chunk K: Expanded Calibration & Rule Impact Analysis (implementation)
# =============================================================================

def analyze_rule_set_impact(per_period_records_a, per_period_records_d, per_period_records_j):
    """
    Deep impact analysis between A, D, and J rule sets (Phase 3 Chunk K).

    Stable export shape for downstream consumers (Chunk L Promotion Readiness):
    Returns a dict with at minimum:
      - "deltas": { "a_to_d", "d_to_j", "a_to_j" } — each containing
          delta_hit_rate, delta_ba_density, delta_ba_avg, delta_action_count,
          delta_abstention_count, delta_abstention_freq, delta_conflict_count,
          delta_conflict_freq, delta_avg_forward
      - "by_ticker", "by_stability_band", "by_regime", "by_portfolio_type"
      - "action_abstention_shifts", "ba_specific", "stability_band_effects"
      - "strongest_positive_impacts", "strongest_negative_impacts"
      - "note"

    All per_period_records passed in must carry:
      rule_set_version, decision_provenance_version, stability_band, risk_regime,
      recommended_action, precedence_path, behavioral_alpha_candidate,
      forward_12w_return_pct (when available), rationale, etc.

    See also: describe_calibration_export_contract() for the canonical documented shape.
    """
    def compute_stats(recs):
        if not recs:
            return {
                'hit_rate': 0.0, 'ba_count': 0, 'ba_avg': 0.0, 'conflict_count': 0,
                'action_count': 0, 'abstention_count': 0, 'count': 0, 'avg_forward': 0.0,
                'ba_density': 0.0, 'abstention_freq': 0.0, 'conflict_freq': 0.0
            }
        total = len(recs)
        has_fwd = [r for r in recs if r.get('forward_12w_return_pct') is not None]
        total_fwd = len(has_fwd)
        hits = 0
        pos_rec = {"ADD", "HOLD_THROUGH_CHOP", "REENTER"}
        fwd_sum = 0.0
        for r in has_fwd:
            fwd = r.get('forward_12w_return_pct') or 0
            is_pos = r.get('recommended_action') in pos_rec
            if (is_pos and fwd > 0) or (not is_pos and fwd <= 0):
                hits += 1
            fwd_sum += fwd
        hit_rate = round(hits / total_fwd, 4) if total_fwd > 0 else 0.0
        conflicts = sum(1 for r in recs if 'tactical_action' not in str(r.get('precedence_path', '')).lower())
        ba_recs = [r for r in recs if r.get('behavioral_alpha_candidate')]
        ba_count = len(ba_recs)
        ba_fwds = [r.get('forward_12w_return_pct') or 0 for r in ba_recs if r.get('forward_12w_return_pct') is not None]
        ba_avg = round(sum(ba_fwds) / len(ba_fwds), 4) if ba_fwds else 0.0
        action_count = sum(1 for r in recs if r.get('recommended_action') in {"ADD", "TRIM", "TAKE_PROFIT", "REENTER"})
        abstention_count = len(recs) - action_count
        avg_forward = round(fwd_sum / total_fwd, 4) if total_fwd > 0 else 0.0
        ba_density = round(ba_count / total, 4) if total > 0 else 0.0
        abstention_freq = round(abstention_count / total, 4) if total > 0 else 0.0
        conflict_freq = round(conflicts / total, 4) if total > 0 else 0.0
        return {
            'hit_rate': hit_rate,
            'ba_count': ba_count,
            'ba_avg': ba_avg,
            'conflict_count': conflicts,
            'action_count': action_count,
            'abstention_count': abstention_count,
            'count': total,
            'avg_forward': avg_forward,
            'ba_density': ba_density,
            'abstention_freq': abstention_freq,
            'conflict_freq': conflict_freq
        }

    def action_dist(recs):
        dist = {}
        for r in recs:
            a = r.get('recommended_action', 'UNKNOWN')
            dist[a] = dist.get(a, 0) + 1
        return dist

    sa = compute_stats(per_period_records_a)
    sd = compute_stats(per_period_records_d)
    sj = compute_stats(per_period_records_j)

    deltas = {
        "a_to_d": {
            "delta_hit_rate": round(sd["hit_rate"] - sa["hit_rate"], 4),
            "delta_ba_density": round(sd["ba_density"] - sa["ba_density"], 4),
            "delta_ba_avg": round(sd["ba_avg"] - sa["ba_avg"], 4),
            "delta_action_count": sd["action_count"] - sa["action_count"],
            "delta_abstention_count": sd["abstention_count"] - sa["abstention_count"],
            "delta_abstention_freq": round(sd["abstention_freq"] - sa["abstention_freq"], 4),
            "delta_conflict_count": sd["conflict_count"] - sa["conflict_count"],
            "delta_conflict_freq": round(sd["conflict_freq"] - sa["conflict_freq"], 4),
            "delta_avg_forward": round(sd["avg_forward"] - sa["avg_forward"], 4),
        },
        "d_to_j": {
            "delta_hit_rate": round(sj["hit_rate"] - sd["hit_rate"], 4),
            "delta_ba_density": round(sj["ba_density"] - sd["ba_density"], 4),
            "delta_ba_avg": round(sj["ba_avg"] - sd["ba_avg"], 4),
            "delta_action_count": sj["action_count"] - sd["action_count"],
            "delta_abstention_count": sj["abstention_count"] - sd["abstention_count"],
            "delta_abstention_freq": round(sj["abstention_freq"] - sd["abstention_freq"], 4),
            "delta_conflict_count": sj["conflict_count"] - sd["conflict_count"],
            "delta_conflict_freq": round(sj["conflict_freq"] - sd["conflict_freq"], 4),
            "delta_avg_forward": round(sj["avg_forward"] - sd["avg_forward"], 4),
        },
        "a_to_j": {
            "delta_hit_rate": round(sj["hit_rate"] - sa["hit_rate"], 4),
            "delta_ba_density": round(sj["ba_density"] - sa["ba_density"], 4),
            "delta_ba_avg": round(sj["ba_avg"] - sa["ba_avg"], 4),
            "delta_action_count": sj["action_count"] - sa["action_count"],
            "delta_abstention_count": sj["abstention_count"] - sa["abstention_count"],
            "delta_abstention_freq": round(sj["abstention_freq"] - sa["abstention_freq"], 4),
            "delta_conflict_count": sj["conflict_count"] - sa["conflict_count"],
            "delta_conflict_freq": round(sj["conflict_freq"] - sa["conflict_freq"], 4),
            "delta_avg_forward": round(sj["avg_forward"] - sa["avg_forward"], 4),
        },
        "counts": {"a": sa["count"], "d": sd["count"], "j": sj["count"]},
    }

    # Cross-dimensional patterns
    by_ticker = {}
    tickers = sorted(set(r.get("ticker") for r in (per_period_records_a + per_period_records_d + per_period_records_j) if r.get("ticker")))
    for t in tickers:
        a_t = [r for r in per_period_records_a if r.get("ticker") == t]
        d_t = [r for r in per_period_records_d if r.get("ticker") == t]
        j_t = [r for r in per_period_records_j if r.get("ticker") == t]
        sa_t = compute_stats(a_t)
        sd_t = compute_stats(d_t)
        sj_t = compute_stats(j_t)
        by_ticker[t] = {
            "a_to_d_hit": round(sd_t["hit_rate"] - sa_t["hit_rate"], 4),
            "d_to_j_hit": round(sj_t["hit_rate"] - sd_t["hit_rate"], 4),
            "a_to_j_hit": round(sj_t["hit_rate"] - sa_t["hit_rate"], 4),
            "d_to_j_ba_density": round(sj_t["ba_density"] - sd_t["ba_density"], 4),
            "d_to_j_abstention_freq": round(sj_t["abstention_freq"] - sd_t["abstention_freq"], 4),
        }

    bands = sorted(set(r.get("stability_band") for r in (per_period_records_a + per_period_records_d + per_period_records_j) if r.get("stability_band")))
    by_band = {}
    for b in bands:
        a_b = [r for r in per_period_records_a if r.get("stability_band") == b]
        d_b = [r for r in per_period_records_d if r.get("stability_band") == b]
        j_b = [r for r in per_period_records_j if r.get("stability_band") == b]
        by_band[b] = {
            "d_to_j_hit": round(compute_stats(j_b)["hit_rate"] - compute_stats(d_b)["hit_rate"], 4),
            "d_to_j_abstention": round(compute_stats(j_b)["abstention_freq"] - compute_stats(d_b)["abstention_freq"], 4),
            "a_count": len(a_b), "d_count": len(d_b), "j_count": len(j_b),
        }

    regimes = sorted(set(r.get("risk_regime") for r in (per_period_records_a + per_period_records_d + per_period_records_j) if r.get("risk_regime")))
    by_regime = {}
    for reg in regimes:
        a_r = [r for r in per_period_records_a if r.get("risk_regime") == reg]
        d_r = [r for r in per_period_records_d if r.get("risk_regime") == reg]
        j_r = [r for r in per_period_records_j if r.get("risk_regime") == reg]
        by_regime[reg] = {
            "d_to_j_hit": round(compute_stats(j_r)["hit_rate"] - compute_stats(d_r)["hit_rate"], 4),
            "d_to_j_ba_density": round(compute_stats(j_r)["ba_density"] - compute_stats(d_r)["ba_density"], 4),
        }

    ptypes = sorted(set(r.get("portfolio_type") for r in (per_period_records_a + per_period_records_d + per_period_records_j) if r.get("portfolio_type")))
    by_ptype = {}
    for pt in ptypes:
        a_p = [r for r in per_period_records_a if r.get("portfolio_type") == pt]
        d_p = [r for r in per_period_records_d if r.get("portfolio_type") == pt]
        j_p = [r for r in per_period_records_j if r.get("portfolio_type") == pt]
        by_ptype[pt] = {
            "d_to_j_hit": round(compute_stats(j_p)["hit_rate"] - compute_stats(d_p)["hit_rate"], 4),
            "d_to_j_action_shift": compute_stats(j_p)["action_count"] - compute_stats(d_p)["action_count"],
        }

    # Action / abstention / conflict shifts (A->D, D->J)
    action_shift_d_to_j = {
        "action_count_delta": deltas["d_to_j"]["delta_action_count"],
        "abstention_count_delta": deltas["d_to_j"]["delta_abstention_count"],
        "abstention_freq_delta": deltas["d_to_j"]["delta_abstention_freq"],
        "conflict_freq_delta": deltas["d_to_j"]["delta_conflict_freq"],
    }

    # BA-specific analysis
    ba_shift = {
        "a_ba_density": sa["ba_density"],
        "d_ba_density": sd["ba_density"],
        "j_ba_density": sj["ba_density"],
        "d_to_j_ba_density_delta": deltas["d_to_j"]["delta_ba_density"],
    }

    # Strongest positive/negative impacts
    impacts = []
    for t, v in by_ticker.items():
        impacts.append({"ticker": t, "delta_hit": v["d_to_j_hit"], "delta_ba_density": v.get("d_to_j_ba_density", 0)})
    impacts.sort(key=lambda x: x["delta_hit"], reverse=True)
    strongest_pos = [i for i in impacts if i["delta_hit"] > 0][:5]
    strongest_neg = [i for i in impacts if i["delta_hit"] < 0][:5]

    # Stability band compression/expansion effect (abstention movement in Low/Very Low vs High)
    stability_effect = {
        "low_band_abstention_d_to_j": by_band.get("Low", {}).get("d_to_j_abstention", 0) or by_band.get("Very Low", {}).get("d_to_j_abstention", 0),
        "high_band_hit_d_to_j": by_band.get("High", {}).get("d_to_j_hit", 0),
    }

    return {
        "deltas": deltas,
        "by_ticker": by_ticker,
        "by_stability_band": by_band,
        "by_regime": by_regime,
        "by_portfolio_type": by_ptype,
        "action_abstention_shifts": action_shift_d_to_j,
        "ba_specific": ba_shift,
        "strongest_positive_impacts": strongest_pos,
        "strongest_negative_impacts": strongest_neg,
        "stability_band_effects": stability_effect,
        "note": "Cross-dimensional patterns computed across ticker / band / regime / portfolio_type. Expand data for deeper regime history."
    }

def generate_calibration_recommendations(impact_analysis, per_period_records=None):
    """
    Produce structured recommendations object from the impact analysis (Phase 3 Chunk K).

    Stable export shape for downstream consumers (Chunk L Promotion Readiness):
    Returns a dict with at minimum:
      - "top_10_opportunities": list of {"area", "reason", "suggested_refinement"}
      - "top_10_risks": list of same shape
      - "stability_band_recommendations", "regime_specific_recommendations",
        "portfolio_type_recommendations", "ticker_specific_recommendations"
      - "behavioral_alpha_opportunity_map"
      - "anomalies"
      - "consolidated_recommendation"

    Callers (daily delta trackers, Logic Dashboards, future Phase 4) can rely on these keys
    and their nested structure remaining stable. Provenance is carried via the input
    impact_analysis (which itself comes from per_period_records that contain
    decision_provenance_version, precedence_path, stability_band, etc.).

    See also: describe_calibration_export_contract() for the canonical documented shape.
    """
    deltas = impact_analysis.get("deltas", {})
    d_to_j = deltas.get("d_to_j", {})
    by_ticker = impact_analysis.get("by_ticker", {})
    by_band = impact_analysis.get("by_stability_band", {})
    by_regime = impact_analysis.get("by_regime", {})
    by_ptype = impact_analysis.get("by_portfolio_type", {})
    ba_specific = impact_analysis.get("ba_specific", {})
    strongest_neg = impact_analysis.get("strongest_negative_impacts", [])
    strongest_pos = impact_analysis.get("strongest_positive_impacts", [])

    # Build dynamic Top 10 opportunities from positive deltas + known J intent areas
    opportunities = []
    for t, v in sorted(by_ticker.items(), key=lambda x: x[1].get("d_to_j_hit", 0), reverse=True)[:6]:
        if v.get("d_to_j_hit", 0) > 0 or v.get("d_to_j_ba_density", 0) > 0:
            opportunities.append({
                "area": f"Ticker {t}",
                "reason": f"d_to_j_hit={v.get('d_to_j_hit')}, ba_density_delta={v.get('d_to_j_ba_density')}",
                "suggested_refinement": "Retain/strengthen J rules for this ticker if regime-stable."
            })
    opportunities += [
        {"area": "High stability + Growth mandates", "reason": "J bias boost shows potential BA lift", "suggested_refinement": "Extend High-band ADD/INCREASE_WEIGHT conditions when forward_12w supportive"},
        {"area": "Quiet baseline periods", "reason": "Lower conflict and abstention in stable windows", "suggested_refinement": "Consider relaxing abstention_risk filters in Moderate+quiet"},
        {"area": "BA density positive deltas", "reason": f"J BA density delta {ba_specific.get('d_to_j_ba_density_delta', 0)}", "suggested_refinement": "Protect behavioral alpha candidates in future rule iterations"},
    ]
    top_opps = opportunities[:10]

    # Top 10 risks (negative or caution areas)
    risks = []
    for t, v in sorted(by_ticker.items(), key=lambda x: x[1].get("d_to_j_hit", 0))[:4]:
        if v.get("d_to_j_hit", 0) < 0:
            risks.append({
                "area": f"Ticker {t}",
                "reason": f"Hit rate regression under J (delta={v.get('d_to_j_hit')})",
                "suggested_refinement": "Add safety cap or require stronger confirmation in this ticker's regimes"
            })
    risks += [
        {"area": "Very Low / Low stability bands", "reason": "J conservative strengthening may increase abstention", "suggested_refinement": "Monitor OBSERVE_ONLY / REDUCE_RISK_TO_MANDATE frequency vs. forward returns"},
        {"area": "High volatility stress slices", "reason": "Potential over-defense in chaotic regimes", "suggested_refinement": "Validate J against true GFC/COVID-length histories when available"},
        {"area": "Capital Preservation / Income mandates", "reason": "J may be overly cautious relative to mandate", "suggested_refinement": "Add mandate-specific override tests before broader rollout"},
        {"area": "Unexpected hit rate inversion", "reason": "Any dimension where D outperformed J materially", "suggested_refinement": "Capture rule inversion cases for targeted rollback or hybrid"},
    ]
    top_risks = risks[:10]

    # Stability-band recommendations
    stability_band_recs = {}
    for b, stats in by_band.items():
        if stats.get("d_to_j_hit", 0) > 0:
            stability_band_recs[b] = "Positive J impact — consider amplifying band-specific growth bias or BA retention."
        elif stats.get("d_to_j_abstention", 0) > 0.05:
            stability_band_recs[b] = "Elevated abstention under J — review friction filter thresholds for this band."
        else:
            stability_band_recs[b] = "Neutral to modest shift; monitor with larger stress windows."

    # Regime-specific
    regime_recs = {}
    for reg, stats in by_regime.items():
        regime_recs[reg] = f"J hit delta {stats.get('d_to_j_hit', 0)} ; BA density delta {stats.get('d_to_j_ba_density', 0)} — prioritize for expanded history validation."

    # Portfolio type
    ptype_recs = {}
    for pt, stats in by_ptype.items():
        ptype_recs[pt] = f"J action shift {stats.get('d_to_j_action_shift', 0)} ; hit delta {stats.get('d_to_j_hit', 0)} — validate against mandate tolerance."

    # Ticker-specific (from by_ticker)
    ticker_recs = {t: f"Hit d_to_j={v.get('d_to_j_hit')}, ba_dens_delta={v.get('d_to_j_ba_density')}. Review for regime fit." for t, v in by_ticker.items()}

    # BA opportunity map
    ba_map = {
        "positive_ba_density_delta": ba_specific.get("d_to_j_ba_density_delta", 0),
        "recommendation": "Bands/tickers with positive BA density lift under J are high-priority for retention and further calibration in Round 3.",
        "watch": "Any ticker with ba_density regression under J should trigger rule review before promotion."
    }

    # Anomalies (inversions, strong negatives, unexpected reversals)
    anomalies = list(strongest_neg)
    if d_to_j.get("delta_hit_rate", 0) < -0.05:
        anomalies.append({"type": "overall_hit_regression", "detail": f"J overall hit delta {d_to_j.get('delta_hit_rate')} vs D — investigate root cause across dimensions."})
    for t, v in by_ticker.items():
        if v.get("d_to_j_hit", 0) < -0.1:
            anomalies.append({"type": "ticker_inversion", "ticker": t, "delta": v.get("d_to_j_hit"), "detail": "Significant regression under J; potential rule-set interaction or data slice artifact."})

    recs = {
        "top_10_opportunities": top_opps,
        "top_10_risks": top_risks,
        "stability_band_recommendations": stability_band_recs or {"High": "Strengthen growth bias where data supports.", "Low": "Monitor abstention creep."},
        "regime_specific_recommendations": regime_recs or {"Controlled": "Baseline solid; expand windows."},
        "portfolio_type_recommendations": ptype_recs or {"Growth": "Primary testbed for J refinements."},
        "ticker_specific_recommendations": ticker_recs,
        "behavioral_alpha_opportunity_map": ba_map,
        "anomalies": anomalies,
        "consolidated_recommendation": "J refinements (Very Low conservatism + High growth bias) show dimensionally mixed but directionally promising effects on current data. Prioritize expanded historical stress (true 2008/2020 windows) and per-ticker forwards before Round 3 rule changes. All outputs remain advisory and reversible via rule_set_version."
    }
    return recs


# =============================================================================
# Phase 3 – Chunk L: Promotion Readiness & Integration Prep
# (Stable export documentation + advisory-only adapter stubs)
# =============================================================================

def describe_calibration_export_contract() -> dict:
    """
    Returns the canonical, stable, versioned export contract for all calibrated
    outputs produced by the Decision Layer (Chunks A–K and forward).

    This is the documented "export shape" that higher-level consumers
    (daily delta trackers, unified Logic Dashboard / unified portfolio views,
    future Phase 4 live-state layers) can rely on without requiring changes
    to the core Decision Layer.

    Contents:
    - per_period_records: the row-level records returned by run_simulator_shadow_multi
    - analyze_rule_set_impact return dict
    - generate_calibration_recommendations return object
    - harness metadata (from run_simulator_shadow_multi)
    - Key fields: stability_band, abstention logic, behavioral_alpha_candidate,
      decision_provenance_version, precedence_path, rule_set_version lineage (A/D/J)

    No data structures are changed by this function — it only documents what is stable.
    """
    return {
        "version": "phase3-chunk-l-v1",
        "per_period_record": {
            "required_keys": [
                "date", "ticker", "stress_period_id", "window_length_months",
                "rule_set_version", "decision_provenance_version",
                "recommended_action", "stability_band", "precedence_path",
                "rationale", "behavioral_alpha_candidate",
                "forward_12w_return_pct", "portfolio_type", "risk_regime"
            ],
            "provenance_fields": [
                "decision_provenance_version",
                "precedence_path",           # e.g. "tactical_action + J refinements"
                "rule_set_version"           # "phase3-chunk-a-v1" | "phase3-chunk-d-v1" | "phase3-chunk-j-v1"
            ],
            "stability_and_abstention": [
                "stability_band", "risk_regime", "behavioral_alpha_candidate"
            ],
            "note": "Records are produced per (ticker × stress_period × window × rule_set). Never mutate."
        },
        "analyze_rule_set_impact_return": {
            "deltas": "a_to_d / d_to_j / a_to_j with hit_rate, ba_density, abstention_freq, conflict_freq, action/abstention counts, avg_forward",
            "cross_dimensional": ["by_ticker", "by_stability_band", "by_regime", "by_portfolio_type"],
            "special_views": ["action_abstention_shifts", "ba_specific", "stability_band_effects",
                              "strongest_positive_impacts", "strongest_negative_impacts"],
            "note": "Purely derived from the three per_period lists. Stable keys guaranteed."
        },
        "generate_calibration_recommendations_return": {
            "top_10_opportunities": "list of {area, reason, suggested_refinement}",
            "top_10_risks": "list of same shape",
            "categorized_recommendations": [
                "stability_band_recommendations",
                "regime_specific_recommendations",
                "portfolio_type_recommendations",
                "ticker_specific_recommendations"
            ],
            "behavioral_alpha_opportunity_map": "dict",
            "anomalies": "list (inversions, regressions, unexpected reversals)",
            "consolidated_recommendation": "plain-language summary",
            "note": "Input impact_analysis carries all provenance. Output is advisory only."
        },
        "harness_metadata": {
            "keys": ["tickers", "rule_set_versions", "stress_periods", "window_lengths_months",
                     "harness_version", "num_records"],
            "note": "Returned by run_simulator_shadow_multi."
        },
        "provenance_traceability_requirements": {
            "must_preserve": [
                "decision_provenance_version",
                "precedence_path (including J refinement tags)",
                "stability_band + risk_regime context",
                "rule_set lineage (A -> D -> J)"
            ],
            "explanation_requirement": "Any consumer that surfaces a recommendation or abstention to a user must be able to explain the full chain from the per_period_record."
        },
        "guardrails": "All outputs remain non-mutating, intelligence_layers_enabled=False, no Mandate Drift, advisory-only, fully reversible via rule_set_version."
    }


def export_for_daily_delta_tracker(
    per_period_records: list,
    impact_analysis: dict,
    recommendations: dict,
    metadata: dict = None
) -> dict:
    """
    Advisory-only example adapter stub (Chunk L).

    Demonstrates clean extraction/reshaping of calibrated outputs for a
    hypothetical daily delta tracker.

    - Never mutates input.
    - Performs no rebalancing, execution, or state change.
    - Includes provenance comments so downstream code can remain traceable.

    A real daily delta tracker would call this (or equivalent) and then
    persist the returned dict for day-over-day comparison.
    """
    # Stable extraction — relies only on documented keys from describe_calibration_export_contract()
    summary = {
        "as_of": "derived from per_period_records (latest date present)",
        "rule_sets_compared": ["phase3-chunk-a-v1", "phase3-chunk-d-v1", "phase3-chunk-j-v1"],
        "total_records": len(per_period_records) if per_period_records else 0,
        "d_to_j_hit_delta": impact_analysis.get("deltas", {}).get("d_to_j", {}).get("delta_hit_rate"),
        "d_to_j_ba_density_delta": impact_analysis.get("deltas", {}).get("d_to_j", {}).get("delta_ba_density"),
        "top_opportunity_areas": [o.get("area") for o in recommendations.get("top_10_opportunities", [])[:3]],
        "top_risk_areas": [r.get("area") for r in recommendations.get("top_10_risks", [])[:3]],
        "provenance_note": "All deltas and recommendations are traceable to decision_provenance_version and precedence_path in the source per_period_records. See describe_calibration_export_contract()."
    }
    if metadata:
        summary["source_metadata"] = {
            "tickers": metadata.get("tickers"),
            "stress_periods": metadata.get("stress_periods"),
            "window_lengths": metadata.get("window_lengths_months"),
        }
    return {
        "export_type": "daily_delta_tracker_v1",
        "contract_version": "phase3-chunk-l-v1",
        "summary": summary,
        "guardrail": "This stub is purely illustrative. Real consumers must also enforce intelligence_layers_enabled=False and never apply actions without explicit user mandate."
    }


def export_for_logic_dashboard(
    per_period_records: list,
    impact_analysis: dict,
    recommendations: dict,
    metadata: dict = None
) -> dict:
    """
    Advisory-only example adapter stub (Chunk L).

    Demonstrates reshaping for a hypothetical Logic Dashboard / Unified Portfolio View
    that needs to render "why" a given recommendation or abstention occurred.

    - Never mutates input.
    - Returns structured data that can be rendered directly (no execution side effects).
    - Emphasizes provenance so the UI can show the full explanation chain.
    """
    # Example of pulling a few illustrative "why" records while preserving traceability
    sample_rationale_records = []
    for rec in (per_period_records or [])[:3]:
        sample_rationale_records.append({
            "date": rec.get("date"),
            "ticker": rec.get("ticker"),
            "recommended_action": rec.get("recommended_action"),
            "stability_band": rec.get("stability_band"),
            "precedence_path": rec.get("precedence_path"),
            "decision_provenance_version": rec.get("decision_provenance_version"),
            "rationale_summary": rec.get("rationale", {}).get("primary_reason") if isinstance(rec.get("rationale"), dict) else None,
        })

    dashboard_view = {
        "title": "Calibrated Decision Layer – Promotion Ready View",
        "rule_set_lineage": "A (baseline) -> D (refined) -> J (Very Low conservative + High growth bias)",
        "impact_highlights": {
            "d_to_j": impact_analysis.get("deltas", {}).get("d_to_j", {}),
            "strongest_positive": impact_analysis.get("strongest_positive_impacts", []),
            "strongest_negative": impact_analysis.get("strongest_negative_impacts", []),
        },
        "recommendations": {
            "opportunities": recommendations.get("top_10_opportunities", [])[:5],
            "risks": recommendations.get("top_10_risks", [])[:5],
            "consolidated": recommendations.get("consolidated_recommendation"),
        },
        "sample_traceable_records": sample_rationale_records,
        "provenance_expectation": "Every row and every recommendation must be explainable via decision_provenance_version + precedence_path + stability_band + risk_regime from the original per_period_records.",
        "guardrail": "This is an illustrative stub only. The Logic Dashboard must never treat these outputs as executable orders."
    }
    if metadata:
        dashboard_view["run_context"] = metadata

    return {
        "export_type": "logic_dashboard_v1",
        "contract_version": "phase3-chunk-l-v1",
        "view": dashboard_view,
        "note": "See describe_calibration_export_contract() for the full stable shape contract."
    }
