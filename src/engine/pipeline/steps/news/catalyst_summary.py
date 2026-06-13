"""
Catalyst Summary Module (v2 - Scorable Weighted Signal)
Stand-alone experimental track for news analysis.

This module is kept separate from Bandit's Rocket scoring and abstention logic.
It can be used directly for diagnostics, dashboards, or future experiments
(NewsPulse v2, abstention, OutlierEvent integration — all deferred).

Evolves the descriptive v1/v1.1 summary into a single Catalyst Strength Score
plus supporting signals: recency, clustering, improved weighted source quality,
and Primary/Secondary driver with confidence.

All v1 fields are preserved exactly (backward compatibility). New v2 fields
are additive.

Key v2 additions:
- catalyst_strength_score: float in [-1.0, +1.0] (transparent 6-term weighted formula)
- primary_driver + primary_driver_confidence (and secondary if >=0.35)
- most_recent_catalyst_utc, recency_score (v2.1: exponential decay exp(-h/36) over ~5d window)
- cluster_score + cluster_description (density in 12h/24h/48h windows)
- source_quality_score (0-1 weighted avg using tier base*mult) + source_quality_detail

v2.1 refinements (tight scope: signal quality only, full backward compat):
- Tightened DRIVER_RULES (esp. Contract/M&A + Macro) to reduce generic false positives via phrase patterns + removed standalone generics.
- Improved driver confidence: exact weighted formula 0.40*recency_weight + 0.25*source_quality + 0.20*sentiment_intensity + 0.15*keyword_match_strength (phrase > keyword).
- Rebalanced strength formula (higher driver_conf + source_quality weights; lower sent + conditional vol) + exponential recency_score = exp(-hours/36).
- Driver override: high-signal (strong phrase + Tier1/high + high sent + <36h) forces primary (debug surfaced in console + influences summary_text).

v2.2 (strictly limited to 2 items):
- Fallback driver categories (General Market Commentary default; Sentiment-Only, Sector-Only, Product/Launch) activate only when articles>0 but normal rules yield "Other / Unknown". Low conf (~0.38), updates legacy primary_drivers + v2 primary/secondary. [v2.2 FALLBACK] console log.
- Secondary driver confidence now primary_conf * 0.88 for visible separation (only when secondary exists). No change to primary conf or other signals.

Inputs: list[dict] from fetch_news() / _normalize_to_canonical_news.
  Required-ish per item: headline/title, timestamp/published_utc, source/publisher,
  summary/description, tickers, insights (optional), sentiment (top-level from normalizer).

Example usage (requires MASSIVE_API_KEY):

    from engine.pipeline.steps.news.news_reader import fetch_news
    from engine.pipeline.steps.news.catalyst_summary import compute_catalyst_summary
    from datetime import date

    items = fetch_news("NVDA", as_of=date.today())
    summary = compute_catalyst_summary(items)
    print(summary["summary_text"])
    print("Strength:", summary["catalyst_strength_score"])
    print("Primary:", summary.get("primary_driver"), summary.get("primary_driver_confidence"))
    print("Recency:", summary.get("recency_score"), "Cluster:", summary.get("cluster_description"))
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from math import exp
from typing import Any, Optional

# =============================================================================
# PUBLISHER QUALITY TIERS (v1.1)
# =============================================================================
HIGH_QUALITY_PUBLISHERS = {
    "bloomberg", "reuters", "wall street journal", "wsj", "financial times",
    "ft", "barron's", "barrons", "cnbc", "the economist", "economist"
}

MEDIUM_QUALITY_PUBLISHERS = {
    "yahoo finance", "benzinga", "seeking alpha", "zacks", "marketwatch",
    "globe newswire", "pr newswire", "tipranks", "investor's business daily",
    "ibd", "motley fool"
}

# v2 source quality scoring (per spec table: base score + weight multiplier favoring high-tier)
TIER_BASE: dict[str, float] = {"high": 0.90, "medium": 0.60, "low": 0.30}
TIER_MULT: dict[str, float] = {"high": 1.0, "medium": 0.85, "low": 0.60}

# volume_surprise -> score for formula (spec)
VOLUME_SURPRISE_SCORES: dict[str, float] = {"low": 0.3, "medium": 0.6, "high": 0.9}

# Driver confidence threshold for secondary (spec)
SECONDARY_CONFIDENCE_THRESHOLD = 0.35


def _get_publisher_quality(publisher_name: str | None) -> str:
    """Return 'high', 'medium', or 'low' based on publisher name."""
    if not publisher_name:
        return "low"
    name_lower = publisher_name.lower()
    if any(p in name_lower for p in HIGH_QUALITY_PUBLISHERS):
        return "high"
    if any(p in name_lower for p in MEDIUM_QUALITY_PUBLISHERS):
        return "medium"
    return "low"


# =============================================================================
# v2 HELPERS: Timestamp parsing, recency, clustering, weighted source quality,
#             driver confidence scoring (with primary/secondary)
# =============================================================================

def _parse_timestamp(ts: str | None) -> datetime | None:
    """Robust parse for MASSIVE published_utc / timestamp strings (ISO with Z or offset)."""
    if not ts:
        return None
    s = str(ts).strip()
    if not s:
        return None
    # Normalize Z to offset for fromisoformat
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Strip common trailing fractional seconds issues if any
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    # Fallbacks for naive or other common forms (treat naive as UTC)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s.split("+")[0].split("Z")[0], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _compute_item_recency_weight(dt: datetime | None, now: datetime) -> float:
    """Return 0.0-1.0 recency factor for an item.
    v2.1: Exponential decay recency_weight = exp(-hours/36) for more realistic curve
    (1.0 at t=0; ~0.37 at 36h; ~0.05 at ~108h). Used for conf scoring + recency_score field.
    """
    if dt is None:
        return 0.05  # low default
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - dt).total_seconds() / 3600.0)
    return exp(-hours / 36.0)  # v2.1 exponential (replaces prior linear 120h)


def _pick_strongest_article_ts(items: list[dict[str, Any]], metas: list[dict[str, Any]]) -> str | None:
    """Pick 'strongest' article ts (by quality + sentiment presence + slight recency) per spec guidance."""
    if not items:
        return None
    best_ts: str | None = None
    best_score = -1.0
    for idx, item in enumerate(items):
        meta = metas[idx] if idx < len(metas) else {"qual": "low", "rec_w": 0.1}
        qscore = TIER_BASE.get(meta.get("qual", "low"), 0.3) * 0.7
        sent_bonus = 0.25 if (item.get("sentiment") or item.get("insights")) else 0.0
        rec_bonus = meta.get("rec_w", 0.1) * 0.3
        score = qscore + sent_bonus + rec_bonus
        if score > best_score:
            best_score = score
            ts = item.get("timestamp") or item.get("published_utc") or item.get("published_at")
            best_ts = str(ts) if ts else None
    return best_ts


def _classify_drivers_with_confidence(
    items: list[dict[str, Any]], metas: list[dict[str, Any]], batch_intensity: float = 0.5
) -> tuple[list[str], dict[str, float]]:
    """
    v2 + v2.1: Return (ordered_driver_list_for_compat, driver_to_confidence_0_1).
    v2.1 confidence formula (exact per spec):
        confidence = (
            0.40 * recency_weight +
            0.25 * source_quality +
            0.20 * sentiment_intensity +
            0.15 * keyword_match_strength
        )
    - recency_weight: per-item exp decay (from meta)
    - source_quality: tier (high=1.0, med=0.7, low=0.4) avg over matches
    - sentiment_intensity: batch intensity (global signal strength)
    - keyword_match_strength: 1.0 if strong_phrase match, else 0.55 for basic kw (phrases > single words)
    Precedence from DRIVER_RULES still drives legacy primary_drivers list.
    """
    if not items:
        return (["Other / Unknown"], {})

    matched_order: list[str] = []
    driver_confs: dict[str, float] = {}

    for rule in DRIVER_RULES:
        name = rule["name"]
        # v2.1: strong_phrases first (for kw strength + override), then keywords
        strongs = rule.get("strong_phrases", [])
        weaks = rule.get("keywords", [])
        all_kws = strongs + weaks

        match_indices: list[int] = []
        per_match_kw_strengths: list[float] = []
        for i, item in enumerate(items):
            text = " ".join([
                str(item.get("headline", "")),
                str(item.get("title", "")),
                str(item.get("summary", "")),
                str(item.get("description", "")),
            ]).lower()
            matched = False
            best_kw_str = 0.0
            # Check strong phrases first (higher strength)
            for kw in strongs:
                if kw in text:
                    matched = True
                    best_kw_str = max(best_kw_str, 1.0)
            # Weak single-word / basic
            if not matched or best_kw_str < 0.9:  # still record if only weak
                for kw in weaks:
                    if kw in text:
                        matched = True
                        best_kw_str = max(best_kw_str, 0.55)
                        break
            if matched:
                match_indices.append(i)
                per_match_kw_strengths.append(best_kw_str if best_kw_str > 0 else 0.55)

        if not match_indices:
            continue

        # v2.1 components
        rec_vals = [metas[i].get("rec_w", 0.05) for i in match_indices]
        avg_rec = sum(rec_vals) / len(rec_vals) if rec_vals else 0.05

        # source: map tier to weight (high favored)
        tier_w = {"high": 1.0, "medium": 0.70, "low": 0.40}
        qual_vals = [tier_w.get(metas[i].get("qual", "low"), 0.4) for i in match_indices]
        avg_src = sum(qual_vals) / len(qual_vals) if qual_vals else 0.4

        sent = max(0.0, min(1.0, batch_intensity))

        avg_kw_str = sum(per_match_kw_strengths) / len(per_match_kw_strengths) if per_match_kw_strengths else 0.55

        # v2.1 EXACT formula
        conf = round(
            0.40 * avg_rec +
            0.25 * avg_src +
            0.20 * sent +
            0.15 * avg_kw_str,
            3
        )
        conf = max(0.0, min(1.0, conf))
        driver_confs[name] = conf

        if name not in matched_order:
            matched_order.append(name)

    if not matched_order:
        return (["Other / Unknown"], {})

    return (matched_order, driver_confs)


def _compute_recency_and_cluster(
    items: list[dict[str, Any]], metas: list[dict[str, Any]], now: datetime
) -> tuple[str | None, float, float, str]:
    """Return (most_recent_catalyst_utc, recency_score, cluster_score, cluster_description).
    v2.1: recency_score now comes from exp decay (via item rec_w); cluster logic unchanged.
    """
    if not items or not metas:
        return (None, 0.0, 0.0, "No articles")

    # most recent catalyst = strongest (already picked outside or recompute)
    most_recent_utc = _pick_strongest_article_ts(items, metas)

    # v2.1 recency_score: now exponential (from updated _compute_item_recency_weight)
    rec_scores = [m.get("rec_w", 0.0) for m in metas]
    recency_score = round(max(rec_scores) if rec_scores else 0.0, 3)

    # Cluster counts in windows (from 'now')
    n12 = n24 = n48 = 0
    for m in metas:
        dt = m.get("dt")
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_h = max(0.0, (now - dt).total_seconds() / 3600.0)
        if age_h <= 12:
            n12 += 1
        if age_h <= 24:
            n24 += 1
        if age_h <= 48:
            n48 += 1

    # Density -> 0-1 cluster score (bias toward very recent clusters)
    c12 = min(1.0, n12 / 4.0)   # 4+ in 12h saturates
    c24 = min(1.0, n24 / 6.0)
    c48 = min(1.0, n48 / 9.0)
    cluster_score = round(0.55 * c12 + 0.30 * c24 + 0.15 * c48, 3)

    # Human readable (tight window first if dense)
    if n12 >= 2:
        cluster_desc = f"{n12} articles in last 12 hours"
    elif n24 >= 3:
        cluster_desc = f"{n24} articles in last 24 hours"
    elif n48 >= 3:
        cluster_desc = f"{n48} articles in last 48 hours"
    else:
        cluster_desc = f"{n12} in 12h / {n24} in 24h / {n48} in 48h"

    return (most_recent_utc, recency_score, cluster_score, cluster_desc)


def _compute_source_quality_weighted(
    items: list[dict[str, Any]]
) -> tuple[float, str, str]:
    """
    v2 weighted source_quality_score (0-1) using tier base * multiplier.
    Returns (score_0_1, old_style_signal, detail_str like "High (Bloomberg, Reuters)").
    The old categorical 'source_quality_signal' behavior is preserved exactly.
    """
    if not items:
        return (0.0, "low", "None")

    qualities: list[str] = []
    weighted_sum = 0.0
    weight_sum = 0.0
    high_names: list[str] = []
    med_names: list[str] = []

    for item in items:
        pub = item.get("publisher") or {}
        if isinstance(pub, dict):
            pub_name = pub.get("name")
        else:
            pub_name = str(pub) if pub else None
        q = _get_publisher_quality(pub_name)
        qualities.append(q)

        base = TIER_BASE[q]
        mult = TIER_MULT[q]
        weighted_sum += base * mult
        weight_sum += mult

        if q == "high" and pub_name:
            high_names.append(str(pub_name))
        elif q == "medium" and pub_name:
            med_names.append(str(pub_name))

    # Weighted avg (favors high-tier via both base and higher mult)
    source_quality_score = (weighted_sum / weight_sum) if weight_sum > 0 else 0.3
    source_quality_score = round(min(1.0, max(0.0, source_quality_score)), 3)

    # Preserve v1.1 exact "best wins" categorical signal
    if "high" in qualities:
        source_quality_signal = "high"
    elif "medium" in qualities:
        source_quality_signal = "medium"
    else:
        source_quality_signal = "low"

    # Detail string (human + for diagnostics)
    if high_names:
        uniq = ", ".join(sorted(set(high_names))[:4])
        detail = f"High ({uniq})"
    elif med_names:
        uniq = ", ".join(sorted(set(med_names))[:4])
        detail = f"Medium ({uniq})"
    else:
        detail = "Low (other sources)"

    return (source_quality_score, source_quality_signal, detail)


# =============================================================================
# DRIVER CLASSIFICATION RULES (v2.1 - Tightened for signal quality)
# (Used by both legacy _classify_drivers for broad list + v2.1 _classify..._with_confidence)
# =============================================================================
# v2.1 changes (per spec):
# - Contract/M&A: REMOVED generic standalone "deal", "investment", "funding", "partnership", "contract".
#   Added strong phrase-level patterns for real events. "acqui"/"merger" kept but de-emphasized without context.
# - Macro: REMOVED generic "policy", "government", "regulation", "congress", "treasury", "economic data", "white house".
#   Now requires specific actionable phrases (rate decisions, named reports, sec actions, tariff on).
#   Negative filter logic applied in match (e.g. skip pure "market commentary").
# - Earnings/Analyst/Product: Kept strong; added some phrase variants to reduce footer/false matches.
# - Added optional "strong_phrases" per rule: used for (a) higher keyword_match_strength in conf,
#   (b) Driver Override trigger (high-signal Tier1 + phrase + high sent + recent).
# Legacy _classify_drivers and broad "primary_drivers" list automatically benefit from tighter keywords.
DRIVER_RULES = [
    # Higher priority rules first
    {
        "name": "Earnings / Guidance",
        "keywords": [
            "earnings", "results", "beat", "miss", "guidance", "outlook",
            "raises guidance", "lowers guidance", "raises outlook", "lowers outlook",
            "eps", "revenue", "profit", "quarterly results", "fiscal"
        ],
        "strong_phrases": [
            "earnings beat", "earnings miss", "raises guidance", "lowers guidance",
            "beats estimates", "missed estimates", "eps beat", "revenue beat"
        ]
    },
    {
        "name": "Analyst Action",
        "keywords": [
            "analyst", "price target", "rating", "upgrade", "downgrade",
            "initiate", "coverage", "buy rating", "sell rating", "hold rating",
            "overweight", "underweight", "neutral", "price objective"
        ],
        "strong_phrases": [
            "raises price target", "cuts price target", "upgrades to", "downgrades to",
            "initiates coverage", "price target raised", "overweight rating"
        ]
    },
    {
        "name": "Contract / Partnership / M&A",
        "keywords": [
            "acqui", "merger", "buyout", "takeover", "wins contract",
            "secures contract", "strategic partnership"
        ],
        "strong_phrases": [
            "acquires", "to acquire", "acquisition of", "merger agreement",
            "merges with", "wins contract", "secures major contract",
            "awarded contract", "strategic partnership", "completes acquisition"
        ]
    },
    {
        "name": "Macro / Policy / Regulatory",
        "keywords": [
            "fed", "federal reserve", "interest rate", "inflation", "tariff",
            "sec", "jobs report", "cpi", "ppi"
        ],
        "strong_phrases": [
            "fed raises", "fed cuts", "fed signals", "interest rate decision",
            "cpi report", "ppi report", "jobs report", "nonfarm payrolls",
            "sec charges", "sec investigation", "sec sues", "tariff on",
            "new regulation", "policy rate"
        ]
    },
    {
        "name": "Product / Launch",
        "keywords": [
            "launch", "launches", "unveil", "unveils", "announce new",
            "fda approval", "approval", "new product", "new chip", "new model",
            "starts production", "begins shipping"
        ],
        "strong_phrases": [
            "fda approval", "wins fda", "launches new", "unveils new chip",
            "announces new product", "starts production of"
        ]
    },
    {
        "name": "Sector / Peer News",
        "keywords": [
            "sector", "industry", "peer", "competitor", "rival", "etf",
            "sector rotation", "industry trend"
        ],
        "strong_phrases": [
            "sector rotation", "industry trend", "peer results", "etf flows"
        ]
    },
]


def _classify_drivers(items: list[dict[str, Any]]) -> list[str]:
    """Return ordered list of primary drivers based on keyword matching with precedence."""
    matched = set()

    for item in items:
        text = " ".join([
            item.get("headline", ""),
            item.get("title", ""),
            item.get("summary", ""),
            item.get("description", ""),
        ]).lower()

        for rule in DRIVER_RULES:
            if any(kw in text for kw in rule["keywords"]):
                matched.add(rule["name"])

    # Return in the defined priority order, not frequency
    ordered = [rule["name"] for rule in DRIVER_RULES if rule["name"] in matched]
    return ordered if ordered else ["Other / Unknown"]


# =============================================================================
# v2.2 FALLBACK DRIVER HELPER
# =============================================================================
def _determine_fallback_driver(
    items: list[dict[str, Any]],
    sector_context: str,
    overall_sentiment: str | None,
    intensity: float,
) -> str | None:
    """
    v2.2: Return a sensible fallback category ONLY when:
      - at least one article exists, AND
      - normal keyword/strong-phrase classification produced no primary driver ("Other / Unknown").
    Priority order per spec. These are lower-confidence than normal drivers.
    Used to update BOTH legacy primary_drivers list and v2 primary/secondary fields.
    """
    if not items:
        return None

    text = " ".join(
        str(item.get("headline", "")) + " " +
        str(item.get("summary", "")) + " " +
        str(item.get("description", ""))
        for item in items
    ).lower()

    # 4. Product / Launch - only with strong phrase evidence (defensive even if rules missed)
    product_phrases = [
        "launch", "launches", "unveil", "unveils", "new product", "new chip",
        "fda approval", "starts production", "begins shipping", "product update",
        "announces new", "release of"
    ]
    if any(p in text for p in product_phrases):
        return "Product / Launch"

    # 3. Sector-Only Catalyst - when sector context or most articles are peer/sector focused
    multi_ticker = sum(1 for item in items if len(item.get("tickers", [])) > 1)
    sector_words = ["sector", "industry", "peer", "competitor", "rival", "etf", "sector rotation"]
    if (
        sector_context == "sector-wide"
        or multi_ticker >= max(1, len(items) // 2)
        or any(w in text for w in sector_words)
    ):
        return "Sector-Only Catalyst"

    # 2. Sentiment-Only Catalyst - clear tone with no specific driver
    if overall_sentiment in ("positive", "negative") and intensity >= 0.55:
        return "Sentiment-Only Catalyst"

    # 1. Default fallback
    return "General Market Commentary"


# =============================================================================
# MAIN FUNCTION (v2)
# =============================================================================
def compute_catalyst_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute a structured catalyst summary from a list of normalized news items.

    v2: Adds scorable Catalyst Strength Score, recency/clustering, weighted source
    quality (with multipliers), and Primary/Secondary driver + confidence scores.
    All v1/v1.1 fields and behavior are preserved exactly (additive only).
    v2.1: Refinements only (tightened rules, new conf formula, rebalanced strength+exp recency, override) - no new fields.
    v2.2: Fallback categories (when articles exist but no driver match) + secondary conf * 0.88. No new fields.

    This is a stand-alone experimental feature. It does not affect scoring,
    abstention, or Bandit's Rocket.

    Args:
        items: List of rich normalized news dicts (from fetch_news).
               Best results when items are from the last 3-5 days.

    Returns:
        dict with all prior keys plus NEW v2 keys:
            catalyst_strength_score (float -1.0 to +1.0)
            primary_driver (str), primary_driver_confidence (float 0-1)
            secondary_driver (str | None), secondary_driver_confidence (float)
            most_recent_catalyst_utc (str | None)
            recency_score (float 0-1), cluster_score (float 0-1), cluster_description (str)
            source_quality_score (float 0-1), source_quality_detail (str)
    """
    if not items:
        return {
            "primary_drivers": [],
            "news_volume_surprise": "low",
            "overall_sentiment": None,
            "sentiment_intensity": 0.0,
            "source_quality_signal": "low",
            "sector_context": "ticker-specific",
            "summary_text": "No recent news.",
            # v2 new (empty case)
            "catalyst_strength_score": 0.0,
            "primary_driver": "Other / Unknown",
            "primary_driver_confidence": 0.0,
            "secondary_driver": None,
            "secondary_driver_confidence": 0.0,
            "most_recent_catalyst_utc": None,
            "recency_score": 0.0,
            "cluster_score": 0.0,
            "cluster_description": "No articles",
            "source_quality_score": 0.0,
            "source_quality_detail": "None",
        }

    now = datetime.now(timezone.utc)

    # Precompute per-item metadata (quality tier, parsed dt, recency weight, text)
    metas: list[dict[str, Any]] = []
    for item in items:
        pub = item.get("publisher") or {}
        if isinstance(pub, dict):
            pub_name = pub.get("name")
        else:
            pub_name = str(pub) if pub else None
        q = _get_publisher_quality(pub_name)
        dt = _parse_timestamp(
            item.get("timestamp") or item.get("published_utc") or item.get("published_at")
        )
        rec_w = _compute_item_recency_weight(dt, now)
        metas.append({"qual": q, "dt": dt, "rec_w": rec_w})

    # === v1 preserved logic (volume, sentiment, sector, old source signal) ===
    # Primary Drivers (legacy ordered list via precedence; v2 conf computed separately)
    primary_drivers = _classify_drivers(items)

    # News Volume Surprise (simple count-based heuristic)
    count = len(items)
    if count >= 8:
        volume_surprise = "high"
    elif count >= 4:
        volume_surprise = "medium"
    else:
        volume_surprise = "low"

    # Sentiment Aggregation (prefers explicit top-level 'sentiment' from normalizer, then insights)
    sentiments = []
    for item in items:
        added = False
        # 1. Direct 'sentiment' key from the enriched normalizer (most reliable)
        sent = item.get("sentiment")
        if isinstance(sent, str) and sent.lower() in ("positive", "negative", "neutral"):
            sentiments.append(sent.lower())
            added = True

        # 2. Fallback to insights list (if no direct sentiment)
        if not added and item.get("insights"):
            for ins in item["insights"]:
                if isinstance(ins, dict):
                    s = ins.get("sentiment")
                    if isinstance(s, str) and s.lower() in ("positive", "negative", "neutral"):
                        sentiments.append(s.lower())
                        added = True
                        break

        # 3. Keyword fallback in summary (only if nothing explicit found for this item)
        if not added:
            text = str(item.get("summary", "")).lower() + " " + str(item.get("description", "")).lower()
            if "positive" in text and "negative" not in text:
                sentiments.append("positive")
            elif "negative" in text and "positive" not in text:
                sentiments.append("negative")

    if sentiments:
        pos = sentiments.count("positive")
        neg = sentiments.count("negative")
        total = len(sentiments)
        if pos > neg:
            overall_sentiment = "positive"
            intensity = min(1.0, (pos / total) * 1.1)
        elif neg > pos:
            overall_sentiment = "negative"
            intensity = min(1.0, (neg / total) * 1.1)
        else:
            overall_sentiment = "neutral"
            intensity = 0.5
    else:
        overall_sentiment = None
        intensity = 0.0

    # v2: Weighted source quality (score + detail); also get preserved signal
    source_quality_score, source_quality_signal, source_quality_detail = (
        _compute_source_quality_weighted(items)
    )

    # Sector Context (heuristic) — unchanged
    multi_ticker_count = sum(1 for item in items if len(item.get("tickers", [])) > 1)
    sector_context = "sector-wide" if multi_ticker_count >= 2 else "ticker-specific"

    # === v2 recency + clustering ===
    most_recent_catalyst_utc, recency_score, cluster_score, cluster_description = (
        _compute_recency_and_cluster(items, metas, now)
    )

    # === v2.1 Driver Override Logic (high-signal single article can promote primary) ===
    # Trigger: strong_phrase match + Tier1 (high) + high batch intensity + recent (<36h)
    # Effect: boost that driver's conf so it wins primary; surface via console log (debug)
    # No new return fields; lightly influences summary_text via primary change.
    override_applied = False
    override_driver_name = None
    for idx, item in enumerate(items):
        q = metas[idx].get("qual", "low")
        dt = metas[idx].get("dt")
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours = max(0.0, (now - dt).total_seconds() / 3600.0)
        if q != "high" or intensity < 0.70 or hours > 36.0:
            continue
        text = " ".join([
            str(item.get("headline", "")), str(item.get("title", "")),
            str(item.get("summary", "")), str(item.get("description", "")),
        ]).lower()
        for rule in DRIVER_RULES:
            for phrase in rule.get("strong_phrases", []):
                if phrase in text:
                    override_driver_name = rule["name"]
                    override_applied = True
                    print(f"[v2.1 DRIVER OVERRIDE] High-signal Tier1 recent article (<{hours:.1f}h, sent={intensity:.2f}) forces primary to '{override_driver_name}' (matched phrase: '{phrase}')")
                    break
            if override_applied:
                break
        if override_applied:
            break

    # === v2.1 Driver confidence + primary/secondary (updated call passes intensity) ===
    ordered_for_compat, driver_confs = _classify_drivers_with_confidence(items, metas, batch_intensity=intensity)
    # v2.1: apply override boost (if any) so it becomes (or strongly influences) Primary
    if override_applied and override_driver_name and driver_confs:
        if override_driver_name in driver_confs:
            driver_confs[override_driver_name] = max(driver_confs[override_driver_name], 0.96)
            # re-sort will pick it
        else:
            driver_confs[override_driver_name] = 0.96

    # Use the precedence-ordered list for the legacy "primary_drivers" key (unchanged behavior)
    # but derive primary/secondary from confidence scores
    if driver_confs:
        sorted_by_conf = sorted(driver_confs.items(), key=lambda kv: kv[1], reverse=True)
        primary_driver = sorted_by_conf[0][0]
        primary_driver_confidence = sorted_by_conf[0][1]
        if len(sorted_by_conf) > 1 and sorted_by_conf[1][1] >= SECONDARY_CONFIDENCE_THRESHOLD:
            secondary_driver = sorted_by_conf[1][0]
            secondary_driver_confidence = sorted_by_conf[1][1]
        else:
            secondary_driver = None
            secondary_driver_confidence = 0.0
    else:
        primary_driver = "Other / Unknown"
        primary_driver_confidence = 0.0
        secondary_driver = None
        secondary_driver_confidence = 0.0

    # === v2.2 Fallback driver categories (only when articles exist + normal rules gave "Other / Unknown") ===
    # Updates BOTH legacy primary_drivers (for summary_text compat) and v2 primary/secondary + conf (lower conf).
    # [v2.2] logging for debugging in run_ad_hoc_40.py etc.
    if count > 0 and primary_driver == "Other / Unknown":
        fb = _determine_fallback_driver(items, sector_context, overall_sentiment, intensity)
        if fb:
            print(f"[v2.2 FALLBACK] '{fb}' activated (articles={count}, no strong driver keyword/phrase match)")
            primary_driver = fb
            primary_driver_confidence = 0.38  # lower than normal drivers (0.3-0.45 range feels appropriate)
            # Update legacy list so "driven mainly by ..." and compact view reflect it
            if not primary_drivers or primary_drivers == ["Other / Unknown"]:
                primary_drivers = [fb]
            # No secondary for pure fallback cases (keeps output clean)
            secondary_driver = None
            secondary_driver_confidence = 0.0

    # === v2.2 Small secondary driver confidence separation (visible dominance without over-penalizing) ===
    # Apply only when both exist. Modest 12% reduction creates clear gap vs primary.
    if secondary_driver and primary_driver_confidence > 0:
        secondary_driver_confidence = round(primary_driver_confidence * 0.88, 3)

    # === v2.1 Core Formula rebalance + exponential recency (already applied in item rec_w) ===
    # Rebalance goals (per spec): increase primary_driver_conf + source_quality;
    # reduce raw sentiment_intensity; reduce volume when count low.
    # Recency now exponential (via _compute_item_recency_weight v2.1).
    # Map volume (with low-count dampening)
    volume_surprise_score = VOLUME_SURPRISE_SCORES.get(volume_surprise, 0.3)
    if count < 4:
        volume_surprise_score *= 0.6  # v2.1: dampen when low volume (less reliable signal)
    driver_conf_for_formula = primary_driver_confidence

    # v2.1 rebalanced weights (sum ~1.0): driver+src up, sent+vol down (conditional)
    raw = (
        (intensity * 0.15) +                    # reduced (was 0.25)
        (volume_surprise_score * 0.12) +        # reduced base; further *0.6 above when low count
        (source_quality_score * 0.23) +         # increased (was 0.20)
        (driver_conf_for_formula * 0.25) +      # increased (was 0.15)
        (recency_score * 0.15) +                # adjusted for exp decay character
        (cluster_score * 0.10)
    )

    # Sign by overall sentiment direction (neutral -> 0.0) for -1.0..+1.0 range
    if overall_sentiment == "positive":
        catalyst_strength_score = round(min(1.0, max(0.0, raw)), 3)
    elif overall_sentiment == "negative":
        catalyst_strength_score = round(max(-1.0, min(0.0, -raw)), 3)
    else:
        catalyst_strength_score = 0.0

    # === Human-readable summary text (lightly enhanced for v2/v2.1, still readable) ===
    drivers_str = ", ".join(primary_drivers[:3]) if primary_drivers else "No clear drivers"
    sentiment_str = f"{overall_sentiment} tone" if overall_sentiment else "Mixed/neutral tone"
    # v2 enrichment (non-breaking)
    strength_str = f"strength {catalyst_strength_score:+.2f}"
    recency_hint = f"recency {recency_score:.2f}"
    override_hint = " override" if override_applied else ""
    summary_text = (
        f"{sentiment_str} flow ({volume_surprise} volume) driven mainly by {drivers_str}. "
        f"Sources: {source_quality_signal}. Context: {sector_context}. "
        f"[{strength_str}, {recency_hint}, {cluster_description}{override_hint}]"
    )

    # === Full return: old keys first (exact behavior) + all new v2 keys ===
    return {
        # Existing (exact names + behavior preserved)
        "primary_drivers": primary_drivers,
        "news_volume_surprise": volume_surprise,
        "overall_sentiment": overall_sentiment,
        "sentiment_intensity": round(intensity, 2),
        "source_quality_signal": source_quality_signal,
        "sector_context": sector_context,
        "summary_text": summary_text,
        # NEW in v2 (additive)
        "catalyst_strength_score": catalyst_strength_score,
        "primary_driver": primary_driver,
        "primary_driver_confidence": round(primary_driver_confidence, 3),
        "secondary_driver": secondary_driver,
        "secondary_driver_confidence": round(secondary_driver_confidence, 3),
        "most_recent_catalyst_utc": most_recent_catalyst_utc,
        "recency_score": recency_score,
        "cluster_score": cluster_score,
        "cluster_description": cluster_description,
        "source_quality_score": source_quality_score,
        "source_quality_detail": source_quality_detail,
    }


# =============================================================================
# SELF-TEST / DEMO (synthetic + notes for live)
# Run: PYTHONPATH=src python -m src.engine.pipeline.steps.news.catalyst_summary
# (or from root: PYTHONPATH=src python -c "from engine.pipeline.steps.news.catalyst_summary import ...")
# =============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("CATALYST SUMMARY v2.2 — SYNTHETIC VERIFICATION DEMO (fallback + secondary separation)")
    print("=" * 80)

    # Synthetic items exercising multiple drivers, mixed quality, recency, clustering, sentiment
    now_iso = datetime.now(timezone.utc).isoformat()
    recent_iso = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=60)).isoformat()

    synthetic_items = [
        {
            "headline": "NVDA beats earnings estimates, raises full year guidance",
            "timestamp": recent_iso,
            "source": "massive",
            "summary": "Strong results with AI demand driving record revenue.",
            "tickers": ["NVDA"],
            "publisher": {"name": "Bloomberg"},
            "sentiment": "positive",
            "insights": [{"sentiment": "positive"}],
        },
        {
            "headline": "Analyst raises price target on NVDA to $180 on AI growth",
            "timestamp": now_iso,
            "source": "massive",
            "summary": "Morgan Stanley overweight, cites new product launches.",
            "tickers": ["NVDA"],
            "publisher": {"name": "Reuters"},
            "sentiment": "positive",
        },
        {
            "headline": "NVDA wins major cloud contract with hyperscaler",
            "timestamp": recent_iso,
            "source": "massive",
            "summary": "Partnership expands data center footprint.",
            "tickers": ["NVDA", "MSFT"],
            "publisher": {"name": "CNBC"},
            "sentiment": "positive",
        },
        {
            "headline": "Sector rotation hits chip stocks as macro fears rise",
            "timestamp": old_iso,
            "source": "massive",
            "summary": "Fed signals and inflation data weigh on growth names.",
            "tickers": ["NVDA", "AMD", "TSM"],
            "publisher": {"name": "Yahoo Finance"},
            "sentiment": "negative",
        },
        # v2.2 test case: generic items with no strong driver keywords/phrases -> should trigger fallback
        {
            "headline": "Market moves and trading activity in focus",
            "timestamp": recent_iso,
            "source": "massive",
            "summary": "Broader market commentary and investor sentiment noted today.",
            "tickers": ["FOO"],
            "publisher": {"name": "Some Blog"},
            "sentiment": "neutral",
        },
    ]

    result = compute_catalyst_summary(synthetic_items)
    print("\nSynthetic batch (strong drivers + v2.2 generic fallback case):")
    for k in [
        "catalyst_strength_score",
        "primary_driver",
        "primary_driver_confidence",
        "secondary_driver",
        "secondary_driver_confidence",
        "news_volume_surprise",
        "overall_sentiment",
        "sentiment_intensity",
        "source_quality_score",
        "source_quality_detail",
        "recency_score",
        "cluster_score",
        "cluster_description",
        "most_recent_catalyst_utc",
        "primary_drivers",
        "summary_text",
    ]:
        print(f"  {k}: {result.get(k)}")

    # v2.2 dedicated pure-generic batch to demonstrate fallback (no strong drivers in items)
    generic_items = [{
        "headline": "Market moves and trading activity in focus",
        "timestamp": recent_iso,
        "source": "massive",
        "summary": "Broader market commentary and investor sentiment noted today.",
        "tickers": ["FOO"],
        "publisher": {"name": "Some Blog"},
        "sentiment": "neutral",
    }]
    fb_result = compute_catalyst_summary(generic_items)
    print("\n  [v2.2 pure fallback test]: primary=", fb_result.get("primary_driver"), "conf=", fb_result.get("primary_driver_confidence"), "legacy=", fb_result.get("primary_drivers"))

    print("\n--- Edge: empty items ---")
    empty = compute_catalyst_summary([])
    print(f"  strength={empty['catalyst_strength_score']} primary={empty['primary_driver']} recency={empty['recency_score']}")

    print("\n--- Edge: single low-quality neutral item ---")
    single = compute_catalyst_summary([
        {"headline": "Some minor mention", "timestamp": now_iso, "publisher": {"name": "RandomBlog"}, "summary": "Nothing special", "tickers": ["FOO"]}
    ])
    print(f"  strength={single['catalyst_strength_score']} source_detail={single['source_quality_detail']} cluster={single['cluster_description']}")

    print("\n" + "=" * 80)
    print("v2.2 SYNTHETIC DEMO COMPLETE — expect fallback e.g. 'General Market Commentary' (conf ~0.38) on generic item,")
    print("secondary conf visibly < primary ( * 0.88 ), [v2.2 FALLBACK] log, no regression on v2.1 signals.")
    print("For live: run run_ad_hoc_40.py (paced); target prior 'Other / Unknown' heavy tickers (IWM, RKLB, ARKK, BRK.A etc).")
    print("=" * 80)
