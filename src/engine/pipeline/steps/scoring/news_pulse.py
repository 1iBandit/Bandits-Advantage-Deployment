"""
News Pulse component for Bandit's Rocket v3.1 (Phase 3+).

This module provides the News Pulse signal used as the 5% weighting
component inside compute_rocket_score().

CURRENT STATUS: STAGED v2 HEURISTIC (Phase 5.1)
-----------------------------------------------
The legacy news_pulse() still returns 0.0 (reserving the 5% slot).

The richer compute_news_pulse() now uses a staged conservative heuristic on
raw_news (v1: volume + pos/neg keywords; v2: high-volume count + earnings flag).

All adjustments are bounded (±3% cap on impact_pct) and negative takes precedence.
Future real sentiment/NLP will replace the keyword+volume logic.

The design keeps the overall Rocket formula and scale completely unchanged.
All functions in this module are pure (no I/O, no side effects).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Any, Optional, Union

from .scoring_config import ScoringConfig, DEFAULT_SCORING_CONFIG

# Import the news reader stub to establish the data flow for future NewsPulse integration
from ..news.news_reader import fetch_news

# Lazy import to avoid circular dependency with models
def _get_engine_config():
    from engine.models.core import EngineConfig
    return EngineConfig


# Type alias matching the pattern used in rocket.py and score_ticker.py
FeatureInput = Union[dict[str, Any], Any]


def news_pulse(
    features: Optional[FeatureInput] = None,
    config: Optional[ScoringConfig] = None,
) -> float:
    """
    Compute the News Pulse component for Bandit's Rocket v3.1.

    This is currently a deliberate placeholder that always returns 0.0.

    Args:
        features: Optional features (TickerFeatures or dict). Currently ignored.
                  Future versions may extract news-related signals from here
                  or from an enriched feature object.
        config: Optional ScoringConfig. Currently ignored. Future versions
                may use config values to scale or gate the news contribution.

    Returns:
        float: Always 0.0 in the current implementation.

    Notes:
        - The 5% weight (rocket_news_weight) is already wired in
          compute_rocket_score() and ScoringConfig.
        - Adding a real implementation here will automatically participate
          in the weighted sum without any other code changes.
        - This function is intentionally side-effect free and easy to replace.
    """
    # Explicit placeholder — no features or config are used yet.
    # This line makes the intent unmistakable for future developers.
    _ = features, config  # reserved for future use

    return 0.0


# Quick demo when run directly
if __name__ == "__main__":
    print("News Pulse (stub):", news_pulse())
    print("This component currently contributes exactly 0.0 to Bandit's Rocket v3.1.")
    print("The 5% weight slot is reserved in ScoringConfig.rocket_news_weight.")


# =============================================================================
# Phase 3+ News Pulse Layer (post-Rocket, with gating + diagnostics)
#
# Now includes light inspection of raw_news inside compute_news_pulse
# (conservative keyword heuristic, bounded ±3% impact). Still early scaffolding.
# =============================================================================

@dataclass
class NewsPulseResult:
    """
    Structured result from news / event analysis for a specific ticker on a date.

    This is the primary output of compute_news_pulse and input to apply_news_pulse.
    Designed to be easy to stub, serialize, or replace with a real data source.

    raw_news holds the raw items returned by fetch_news (list of dicts) for
    downstream processing in future NewsPulse implementations.
    """
    trade_gate: int = 1          # +1 = allow news influence, -1 = dampen/block
    news_score: float = 4.5      # 0-10 scale (higher = stronger positive/negative news)
    event_score: float = 4.5     # 0-10 scale for discrete events (earnings, etc.)
    encoded: str = "N45"         # Compact code for notes (e.g. "N45", "E72+")
    impact_pct: float = 0.0      # Suggested % adjustment to apply to rocket score
    raw_news: list[dict] | None = None   # placeholder for fetched news items

    def is_neutral(self) -> bool:
        return abs(self.impact_pct) < 0.1 and self.trade_gate > 0


def compute_news_pulse(
    symbol: str,
    as_of: Date,
    cfg: "EngineConfig",
) -> NewsPulseResult:
    """
    Compute News Pulse signals for a ticker on a given date.

    CURRENT STATUS: STAGED v2 HEURISTIC + RAW NEWS INSPECTION (Phase 5.1)
    ----------------------------------------------------------------------
    Fetches via news_reader, stores raw items, then applies a conservative
    staged heuristic (v1 volume/keywords + v2 volume count + earnings flag)
    to produce small bounded adjustments.

    The heuristic inspects raw_news for:
      - base volume (mild + bias)
      - positive/negative keywords
      - v2: news volume count (if high → modest + tilt)
      - v2: earnings-related high-signal events (stronger but capped tilt)
    Negative always takes precedence. Impact deliberately capped at ~±3% for safety.

    This is staged improvement; future will use real sentiment/NLP.
    """
    # Fetch and store (data flow from Step 2)
    raw_news = fetch_news(symbol, as_of)

    # --- Staged conservative heuristic (Phase 5.1 v2) ---
    # - Non-empty raw_news → mild positive bias (volume = signal)
    # - v2 high news volume count (>5) → modest additional + tilt
    # - Positive keywords → stronger + tilt
    # - v2 earnings high-signal flag → slightly stronger + tilt (if no neg)
    # - Negative keywords → negative tilt (takes full precedence)
    # - Everything bounded: impact_pct ∈ [-3, +3]
    # - encoded updated for diagnostics (visible in CLI notes / Scorecard)
    # - trade_gate stays +1
    # Intentionally conservative; staged for future real NLP.
    news_score = 4.5
    event_score = 4.5
    encoded = "N45"
    impact_pct = 0.0
    trade_gate = 1

    if raw_news:
        # Any news at all gives a tiny positive tilt (volume = mild signal)
        news_score = 5.2
        encoded = "N52"
        impact_pct = 1.2

        n_news = len(raw_news)
        text_blob = " ".join(
            (str(item.get("headline", "")) + " " + str(item.get("summary", ""))).lower()
            for item in raw_news
        )

        # v2: News Volume Signal - if high volume, modest positive tilt
        # (conservative: only if >5 items, small bump)
        if n_news > 5:
            news_score = max(news_score, 5.4)
            impact_pct = min(1.5, impact_pct + 0.3)

        # First-pass positive keyword check (light symmetric addition to negative logic)
        # Gives a modest extra positive tilt when clearly constructive news is present.
        positive_keywords = {
            "beat", "upgrade", "strong", "exceeds", "growth", "record",
            "bullish", "surge", "raised", "outperform", "positive", "above estimates"
        }
        if any(kw in text_blob for kw in positive_keywords):
            news_score = 5.8
            encoded = "N58+"
            impact_pct = 2.2   # still safely under the ±3 cap

        # v2: High-signal earnings event flag (simple keyword match)
        # Earnings/news events are high-signal; apply slightly stronger tilt (capped)
        earnings_keywords = {
            "earnings", "results", "beat", "missed estimates", "guidance",
            "eps", "quarterly", "report"
        }
        is_earnings = any(kw in text_blob for kw in earnings_keywords)
        if is_earnings:
            # stronger but still conservative; if no strong negative, boost
            if not any(kw in text_blob for kw in {"missed", "down", "cut", "warning"}):
                news_score = max(news_score, 5.9)
                encoded = "E62+" if is_earnings else encoded
                impact_pct = min(2.5, impact_pct + 0.4)  # modest extra for earnings

        # Very small, explicit negative keyword list (case-insensitive, headline+summary)
        # Negative takes precedence for conservatism.
        negative_keywords = {
            "downgrade", "lawsuit", "missed", "miss", "recall", "investigation",
            "fraud", "bankrupt", "plunge", "warning", "cut guidance", "cut",
            "loss", "investigated", "charges", "probe"
        }
        if any(kw in text_blob for kw in negative_keywords):
            news_score = 3.8
            encoded = "N38-"
            impact_pct = -2.0

    # Final safety clamp (never more than ~±3% via news for v1/v2 staged)
    impact_pct = max(-3.0, min(3.0, impact_pct))

    return NewsPulseResult(
        trade_gate=trade_gate,
        news_score=news_score,
        event_score=event_score,
        encoded=encoded,
        impact_pct=impact_pct,
        raw_news=raw_news,
    )


def apply_news_pulse(
    rocket_base: float,
    news: NewsPulseResult,
    scoring: ScoringConfig,
) -> float:
    """
    Apply a NewsPulseResult on top of a base Rocket score.

    This is the integration point between the core Rocket calculation and
    the richer News/Event layer.

    Respects trade_gate (severe dampening) and impact_pct (small additive
    adjustment). With the current conservative heuristic, adjustments are
    tiny (±3% max) and the base rocket is almost always returned unchanged
    or with a very small nudge.
    """
    if news.trade_gate < 0:
        # Example gating behavior (can be tuned via ScoringConfig later)
        return rocket_base * 0.6

    if abs(news.impact_pct) < 0.01:
        return rocket_base

    adjustment = rocket_base * (news.impact_pct / 100.0)
    return rocket_base + adjustment
