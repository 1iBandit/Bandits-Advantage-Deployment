"""
Main engine orchestrator (Phase 3).

Wires the full pipeline:
    ingest → compute_features → scoring_step (mandatory) → postprocess → export

Returns an EngineOutput containing:
- `scores`: List[TickerScore]   (rich internal objects, for compatibility)
- `scorecard_rows`: List[ScorecardRow]  (processed, export-oriented rows)

Convenience wrapper: run_with_outlier_detection(config, realized_returns=None, ...)
  Runs the engine and (if realized_returns provided) automatically detects
  and returns OutlierEvents alongside the normal EngineOutput.
"""

from __future__ import annotations

from dotenv import load_dotenv

# Load .env early so API keys are available even when run_engine is imported directly
load_dotenv()

from datetime import datetime, date
from typing import Optional, Dict, Any, List
import uuid
import time
import logging
logger = logging.getLogger(__name__)

import pandas as pd

from engine.models.core import EngineConfig, EngineOutput, TickerScore, OutlierEvent
from engine.pipeline.steps.ingest import ingest
from engine.pipeline.steps.features import compute_features as old_compute_features  # kept for compat
from engine.pipeline.steps.scoring.scoring_step import scoring_step
from engine.pipeline.steps.scoring.scoring_config import ScoringConfig
from engine.pipeline.steps.scoring.expected_range import detect_and_build_outliers
from engine.pipeline.steps.features.compute_features import TickerFeatures as ModernTickerFeatures
from engine.features import compute_features_for_universe
from engine.pipeline.steps.postprocess import postprocess
from engine.models.scorecard import ScorecardRow
from engine.pipeline.universe import build_universe

# For historical replay v1
from datetime import timedelta
from pathlib import Path
from engine.pipeline.steps.news.news_reader import fetch_news
from engine.pipeline.steps.news.catalyst_summary import compute_catalyst_summary
from engine.pipeline.steps.corporate_actions import batch_get_corporate_actions, build_corporate_action_context
from engine.features import compute_features_for_universe
from engine.io.readers import fetch_polygon_ohlcv
from engine.models.core import EngineConfig, TickerScore  # ensure for pt config + PIT scoring construction
# generate_synthetic_ohlcv imported lazily inside run_historical_daily_analysis (synthetic path) to keep module light and match ingest.py pattern

# Lazy / conditional imports for full_export scoring path (avoid loading heavy scoring unless needed)
# from engine.pipeline.steps.scoring.rocket import compute_rocket_score
# from engine.pipeline.steps.scoring.scoring_config import ScoringConfig
# from engine.pipeline.steps.postprocess import postprocess
# (performed inside the function when full_export)


def run_engine(config: Optional[EngineConfig] = None) -> EngineOutput:
    """
    Execute a complete engine run (Phase 3).

    Flow:
        ingest → compute raw features → scoring_step (mandatory) → postprocess → EngineOutput

    Returns:
        EngineOutput with:
            - scores: List[TickerScore]          (full internal scoring objects)
            - scorecard_rows: List[ScorecardRow] (export-ready rows with rocket_zone, abstention_risk/reason/details (Layer 1), etc.)

    All scoring behavior is driven from the nested `cfg.scoring`.

    See also: run_with_outlier_detection() for a wrapper that auto-detects
    outliers when you supply realized_returns (and optionally corporate_actions for v1 CA sanity).
    """
    cfg = config or EngineConfig(as_of=datetime.now().date())

    # Ensure we have a proper nested scoring config (defensive)
    if not hasattr(cfg, "scoring") or cfg.scoring is None:
        cfg.scoring = ScoringConfig()

    # Early universe resolution (before ingest)
    # This populates the effective ticker list according to ad-hoc vs full-run rules.
    # The resulting list can be used by ingest, features, etc.
    effective_tickers = build_universe(cfg)
    # Make the resolved universe available to downstream steps via config
    cfg.ticker_universe = effective_tickers
    cfg.tickers = effective_tickers  # also populate the ad-hoc field for consistency

    # 1. Ingest
    data: Dict[str, Any] = ingest(cfg)
    prices: Dict[str, pd.DataFrame] = data["prices"]
    spy = data.get("spy")
    as_of: date = data.get("as_of") or cfg.as_of or datetime.now().date()

    # 2. Feature computation (raw dict form for the new scoring layer)
    # We use the lower-level function that returns plain feature dicts,
    # then convert them into the modern TickerFeatures dataclass.
    raw_feature_dicts: Dict[str, Dict[str, float]] = compute_features_for_universe(
        prices, spy_df=spy, config=cfg
    )

    # Only score the effective/requested tickers (ad-hoc or core+dynamic).
    # prices may contain SPY (auto-added for synthetic or present in load) solely
    # to support rs_vs_spy + relative_breadth_score cross-sectional calcs.
    # This ensures ad-hoc --tickers runs report exactly N tickers and exclude
    # benchmark unless user explicitly included it.
    raw_feature_dicts = {
        t: feats for t, feats in raw_feature_dicts.items() if t in effective_tickers
    }

    # Convert to dict[str, TickerFeatures] for the new scoring_step signature
    modern_features: Dict[str, ModernTickerFeatures] = {}
    for ticker, feats in raw_feature_dicts.items():
        modern_features[ticker] = ModernTickerFeatures(
            rsi=feats.get("rsi", 50.0),
            atr_pct=feats.get("atr_pct", 0.0),
            adx=feats.get("adx", 20.0),
            rs_vs_spy=feats.get("rs_vs_spy", 0.0),
            relative_breadth_score=feats.get("relative_breadth_score", 50.0),
            expected_range_12w=feats.get("raw_expected_range_12w", 0.0),
            expected_range_12m=feats.get("raw_expected_range_12m", 0.0),
            short_term_movement_intensity=feats.get("short_term_movement_intensity", 0.0),
            momentum_pulse=feats.get("momentum_pulse", 0.0),
            # Acceleration v1 (from legacy dicts; safe defaults)
            rsi_acceleration=feats.get("rsi_acceleration", 0.0),
            volatility_expansion_flag=feats.get("volatility_expansion_flag", 0.0),
        )

    # 3. Scoring (MANDATORY per Phase 3 design)
    # We pass `prices` directly — `scoring_step` extracts the latest close
    # for each ticker and builds complete TickerScore objects.
    scored_dict: Dict[str, TickerScore] = scoring_step(
        modern_features,
        cfg,
        prices=prices,
        as_of=as_of,
    )

    # Alternative (equivalent):
    # from engine.pipeline.steps.scoring import build_identity_from_prices
    # identity = build_identity_from_prices(prices, as_of=as_of)
    # scored_dict = scoring_step(modern_features, cfg, identity=identity)

    final_scores_list = list(scored_dict.values())

    # 4. Postprocess → produces export-ready ScorecardRow objects
    # v1.0: pass corporate_actions (rich dict) from ingest for context building
    ca_dict = data.get("corporate_actions") if isinstance(data, dict) else None
    scorecard_rows: List[ScorecardRow] = postprocess(final_scores_list, cfg, corporate_actions=ca_dict)

    # 5. Assemble final EngineOutput
    spy_close = None
    if spy is not None and not spy.empty:
        spy_close = float(spy["Close"].iloc[-1])

    output = EngineOutput(
        run_id=str(uuid.uuid4())[:8],
        as_of=as_of,
        # Keep the rich TickerScore objects for compatibility with existing consumers
        scores=final_scores_list,
        # New Phase 3+ export shape
        scorecard_rows=scorecard_rows,
        spy_stats={
            "spy_close": spy_close,
            "spy_12w_return": None,  # future enhancement
        },
        regime_state=None,  # future
        metadata={
            "corporate_actions": data.get("corporate_actions") if isinstance(data, dict) else None,  # v1.0 for outliers / consumers
            "num_tickers": len(scorecard_rows),
            "data_source": cfg.data_source,
            "phase": "3 - Features + Mandatory Scoring + Postprocess (v3.1)",
            "scoring_config": {
                "min_momentum_pulse": cfg.scoring.min_momentum_pulse,
                "rocket_stm_weight": cfg.scoring.rocket_stm_weight,
            },
        },
    )

    return output


def run_with_outlier_detection(
    config: Optional[EngineConfig] = None,
    realized_returns: Optional[Dict[str, float]] = None,
    threshold_multiplier: float = 2.0,
    corporate_actions: Optional[dict[str, dict]] = None,  # v1.0 for CA sanity in outliers
) -> tuple[EngineOutput, List[OutlierEvent]]:
    """
    Run the engine and automatically return outliers if realized_returns are supplied.

    This is a thin convenience wrapper around run_engine() + detect_and_build_outliers().

    Args:
        config: EngineConfig (same as run_engine).
        realized_returns: Optional dict of ticker -> realized move (e.g. 12w % return).
                          If None or empty, runs normally and returns empty outlier list.
        threshold_multiplier: Passed through to outlier detection (default 2.0).
        corporate_actions: Optional rich per-ticker dict (from ingest) for v1.0 CA sanity checks (recent split, ex-div, dividend cut) inside outlier builder.

    Returns:
        (EngineOutput, List[OutlierEvent])
        - Always the full output from the run.
        - List of outliers (empty if no realized_returns provided or none qualified).

    Typical usage:
        output, outliers = run_with_outlier_detection(
            cfg,
            realized_returns={"AAPL": 27.4, "MSFT": 4.1}
        )
        if outliers:
            save_outliers_to_jsonl(outliers, "surprises.jsonl")
    """
    output = run_engine(config)

    if not realized_returns:
        return output, []

    ca_to_use = corporate_actions
    if ca_to_use is None and hasattr(output, "metadata") and isinstance(output.metadata, dict):
        ca_to_use = output.metadata.get("corporate_actions")
    outliers = detect_and_build_outliers(
        scores=output.scores,
        realized_returns=realized_returns,
        threshold_multiplier=threshold_multiplier,
        corporate_actions=ca_to_use,
    )
    return output, outliers


def _generate_synthetic_catalyst_events(
    ticker: str,
    start_date: date,
    end_date: date,
    seed: int = 123,
    avg_events_per_month: float = 4.5,
) -> list[dict[str, Any]]:
    """
    Internal v1 helper: generate a realistic stream of plausible news events across [start, end]
    for synthetic replay runs. Events use keywords/phrases that trigger the real DRIVER_RULES
    (Earnings, Analyst Action, Contract, Product/Launch, Macro, Sector/Peer) plus rich fields
    (publisher tiers, sentiment, insights) so compute_catalyst_summary v2+ produces varying
    catalyst_strength_score, primary/secondary + conf, recency, cluster, source_quality etc.

    This enables true demonstration of "as-of" catalyst attachment + varying strength in
    historical daily replay without requiring a full historical news archive.
    For real polygon data on past dates, live fetch_news is still used (and filtered).
    """
    import random
    from datetime import datetime as dt, timedelta as td, timezone as tz
    rng = random.Random(seed + hash(ticker) % 10000)

    # Spread events across business-ish days in the window
    total_days = (end_date - start_date).days
    n_events = max(3, int((total_days / 30.0) * avg_events_per_month))

    events: list[dict[str, Any]] = []
    # Base templates keyed by driver family (strong phrases + generic to hit rules + precedence)
    templates = [
        # Earnings / Guidance (strong)
        ("earnings", "beat", "raised guidance", "EPS beat", 0.82, "Bloomberg"),
        ("earnings", "miss", "lowered guidance", "Revenue shortfall", -0.65, "CNBC"),
        # Analyst Action (strong phrases)
        ("analyst", "price target", "raised PT", "Analyst raises price target to $XX", 0.78, "Barron's"),
        ("analyst", "downgrade", "cut rating", "Analyst downgrades citing valuation", -0.55, "Reuters"),
        # Contract / Partnership (strong phrases for v2.1 tightening)
        ("contract", "wins contract", "secures major contract", "Wins strategic multi-year contract", 0.71, "Bloomberg"),
        ("partnership", "strategic partnership", "announces partnership", "Enters strategic partnership", 0.58, "Yahoo Finance"),
        # Product / Launch
        ("product", "new product", "launch", "Announces major product launch and roadmap", 0.66, "TechCrunch"),
        ("product", "FDA approval", "clearance", "Receives FDA clearance for new offering", 0.75, "Reuters"),
        # Macro / Policy / Sector
        ("macro", "rate decision", "inflation", "Fed signals and macro backdrop weigh on sector", -0.35, "WSJ"),
        ("sector", "peer", "industry", "Sector peers report mixed results; rotation continues", 0.12, "Seeking Alpha"),
    ]

    cur = start_date
    for i in range(n_events):
        # Step forward randomly (cluster some days, space others)
        step = rng.randint(3, max(6, total_days // max(1, n_events)))
        cur = cur + td(days=step)
        if cur > end_date:
            break

        fam = rng.choice(templates)
        driver_key, verb, phrase, summary, sent, pub = fam

        # ISO with Z for parser robustness (matches news normalizer expectations)
        ts_str = cur.isoformat() + "T10:00:00Z"

        headline = f"{ticker} {verb} {phrase}"
        item = {
            "headline": headline,
            "timestamp": ts_str,
            "published_utc": ts_str,
            "source": pub,
            "publisher": {"name": pub},
            "summary": summary,
            "description": summary,
            "sentiment": sent + rng.uniform(-0.12, 0.12),
            "sentiment_reasoning": "synthetic for replay",
            "insights": [f"{driver_key} event"],
            "tickers": [ticker],
            "id": f"synth-{ticker}-{i}",
            "url": f"https://example.com/synth/{i}",
        }
        events.append(item)

    # Ensure at least a couple of spaced events even for short windows
    if len(events) < 2:
        mid = start_date + (end_date - start_date) // 2
        events.append({
            "headline": f"{ticker} announces strategic update",
            "timestamp": mid.isoformat() + "T09:30:00Z",
            "published_utc": mid.isoformat() + "T09:30:00Z",
            "source": "Bloomberg",
            "publisher": {"name": "Bloomberg"},
            "summary": "Company provides update on operations and outlook",
            "sentiment": 0.35,
            "insights": ["update"],
            "tickers": [ticker],
        })

    return events


def run_historical_daily_analysis(
    tickers: str | list[str],
    start_date: date,
    end_date: date | None = None,
    buffer_days: int = 100,
    dividend_lookback_days: int = 365 * 3,
    split_lookback_days: int = 365 * 5,
    pause_seconds: float = 2.0,
    output_csv: str | None = None,
    data_source: str = "synthetic",
    synthetic_seed: int = 42,
    full_export: bool = True,
) -> pd.DataFrame:
    """
    Historical Daily Replay / Point-in-Time Analysis Engine (enhanced for full wide export).

    Fetches (or generates) historical daily bars **once** (efficient, uses hardened
    fetch_polygon_ohlcv with batching + exp backoff + cache when data_source="polygon").
    For **each trading day** in [start_date, end_date]:
      - True PIT prefix slice (only bars with Date <= day).
      - Price features computed exclusively on the prefix (no future data leakage).
      - Full Catalyst Summary v2.2 (news filtered published_utc/timestamp <= day; all fields).
      - Full Corporate Actions v1 context (events with ex/split <= day; impact, flags, notes).
      - (when full_export) Bandit's Rocket v3.1, abstention_risk/reason/details (Layer 1),
        final_rank (within the singleton or small context), and enriched notes via postprocess.

    The output DataFrame is "wide" — every engine-calculated field is a column so you can
    do complete data-quality / behavioral analysis offline.

    Rate limits: prices once (batched/resilient), news+CA pre-fetched once then pure filter.
    Per-day try/except + progress logging so a single transient does not kill a 6-month run.

    Args:
        tickers: str or list[str]. The first is the "primary" for which snapshots are emitted
                 (SPY is always pulled for relative features when available).
        start_date / end_date: Trading day window (inclusive). End defaults to today.
        data_source: "polygon" (real historical via Polygon + cache; recommended for this task)
                     or "synthetic" (for dev without keys / future dates).
        full_export: When True (default), also computes rocket + runs a singleton postprocess
                     pass (with day's CA) to populate bandits_rocket, final_rank, abstention_*,
                     rocket_zone, abstention_status, and full enriched notes. Also captures
                     raw OHLCV (open/high/low/close/volume) from the as-of bar.
        output_csv: If given, written (parent dirs created). Timestamped names recommended
                    for repeated runs.

    Returns:
        Wide pd.DataFrame, one row per trading day for the primary ticker. Columns include
        (but are not limited to):

        Price (from Polygon or synthetic bar):
            open, high, low, close, volume

        Core Technical (prefixed feat_* from compute_features_for_universe on PIT slice):
            feat_rsi, feat_atr_pct, feat_adx, feat_momentum_pulse,
            feat_short_term_movement_intensity, feat_rsi_acceleration,
            feat_volatility_expansion_flag, feat_rs_vs_spy, feat_relative_breadth_score,
            feat_raw_expected_range_12w, feat_raw_expected_range_12m, ...

        Bandit's Rocket + Scoring (full_export):
            bandits_rocket, final_rank, abstention_risk, abstention_reason,
            abstention_details (JSON), abstention_status, rocket_zone, scorecard_notes

        Catalyst Summary v2.2 (ALL fields promoted to clean top-level columns for analytics;
            computed via compute_catalyst_summary on news with published <= day; graceful defaults
            when no news):
            catalyst_strength_score, primary_driver, primary_driver_confidence,
            secondary_driver, secondary_driver_confidence,
            overall_sentiment, sentiment_intensity,
            recency_score, cluster_score, cluster_description,
            source_quality_score, source_quality_signal, source_quality_detail,
            most_recent_catalyst_utc,
            news_volume_surprise, news_count, catalyst_summary (full text),
            (plus legacy keys such as primary_drivers, sector_context, ... — all preserved)

        Corporate Actions v1 (flattened from build_corporate_action_context + raw):
            has_recent_split, split_date, split_ratio, split_normalized,
            recent_dividend_cut, dividend_cut_date, dividend_cut_pct,
            ex_div_date, ex_div_amount, is_dividend_payer, dividend_stability,
            impact_score, ca_notes, corporate_action_context (JSON if full)

        Bandit's Rocket / Scoring (full_export; via compute_rocket_score + postprocess on PIT data):
            bandits_rocket, final_rank, rocket_zone

        Abstention Layer (full_export; Layer 1 reasoning + CA hooks):
            abstention_risk, abstention_reason, abstention_details (JSON),
            abstention_status, primary_abstention_reason (top dominant factor, lightweight),
            scorecard_notes (enriched)

        Metadata:
            date, ticker, data_source

    Point-in-Time guarantee: every feat_*, rocket, abstention calc, catalyst, and CA "as_of"
    the day uses only information whose timestamp / index <= day.

    Example (DOCN success criteria run — real data):
        from datetime import date
        from engine.pipeline import run_historical_daily_analysis
        df = run_historical_daily_analysis(
            "DOCN", date(2025,12,1), date(2026,6,6),
            data_source="polygon", full_export=True,
            output_csv="logs/docn_6mo_full_pit_replay.csv"
        )
        assert len(df) >= 130
        print(df[['date','close','feat_rsi','bandits_rocket','abstention_risk','catalyst_strength_score']].head())

    Success (this task):
      - DOCN 2025-12-01..2026-06-06 with polygon produces ~135 rows, realistic prices
        (early Dec close near real historical ~$44 area), all listed column families present.
      - RSI, momentum_pulse, catalyst_strength_score, bandits_rocket, abstention_*,
        CA impact/flags etc. all vary meaningfully across the window.
      - No future leakage; robust to rate limits (pre-fetch + batch + per-day isolation).
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    tickers = [t.upper() for t in tickers]

    if end_date is None:
        end_date = date.today()

    # 1. Prices once (efficient) — synthetic for any ticker / arbitrary (incl. future) ranges; else polygon (real data)
    from_date = start_date - timedelta(days=buffer_days)
    source = (data_source or "synthetic").lower()

    if source == "synthetic":
        # Compute sufficient business-day coverage for buffer + analysis window + margin for indicators
        from engine.data.readers import generate_synthetic_ohlcv  # lazy, matches ingest + keeps run_engine import surface clean
        total_span = (end_date - from_date).days
        n_days = max(80, int(total_span * 5 / 7) + 25)
        all_t = list(dict.fromkeys([*tickers, "SPY"]))
        prices = generate_synthetic_ohlcv(all_t, n_days=n_days, seed=synthetic_seed, start_date=from_date)
        logger.info(f"Synthetic PIT prices generated for {len(prices)} tickers over ~{n_days} business days (seed={synthetic_seed}).")
    else:
        prices = fetch_polygon_ohlcv(
            tickers,
            from_date=from_date,
            to_date=end_date,
            batch_size=10,
            batch_pause_seconds=2.0,
            max_retries=4,
        )

    if not prices:
        raise RuntimeError("No price data available for historical replay (check data_source / keys / cache).")

    spy_df = prices.get("SPY")

    # Pre-fetch news and CA with as_of=end for efficiency, then filter per-day (as_of respected)
    # News/CA are always live (MASSIVE) — no cache for them (by design). Pre-fetch + client filter is the rate-friendly pattern.
    news_cache: dict[str, list[dict]] = {}
    for t in tickers:
        try:
            items = fetch_news(t, as_of=end_date)
            news_cache[t] = items or []
        except Exception as e:
            logger.warning(f"News pre-fetch failed for {t}: {e}")
            news_cache[t] = []

    # If synthetic data_source, inject a seeded, varying catalyst event stream across the *full* [start,end]
    # so that per-day filtering + compute_catalyst_summary produces realistic varying strength/primary/recency/cluster.
    # (Live MASSIVE returns recent items only; this exercises the full "as-of" attachment + v2.2 logic for diagnostics.)
    if source == "synthetic":
        for t in tickers:
            synth_events = _generate_synthetic_catalyst_events(t, start_date, end_date, seed=synthetic_seed + 7)
            # Merge (or replace) so filter <= day still works and real pre-fetch items (if any) can coexist
            existing = news_cache.get(t, [])
            news_cache[t] = existing + synth_events

    # CA pre-fetch (supports as_of for PIT; batch is paced + defensive)
    try:
        ca_full = batch_get_corporate_actions(
            tickers,
            pause_seconds=pause_seconds,
            dividend_lookback_days=dividend_lookback_days,
            split_lookback_days=split_lookback_days,
            as_of=end_date,
        )
    except Exception as e:
        logger.warning(f"CA pre-fetch failed: {e}")
        ca_full = {t: {"dividends": [], "splits": []} for t in tickers}

    # 2. Trading days from the primary ticker's (synthetic or fetched) index
    main_t = tickers[0]
    if main_t not in prices or prices[main_t].empty:
        main_t = next(iter(prices.keys()))
    all_days = prices[main_t].index
    trading_days = sorted([
        (d.date() if hasattr(d, "date") else d)
        for d in all_days
        if start_date <= (d.date() if hasattr(d, "date") else d) <= end_date
    ])

    snapshots = []
    n_days = len(trading_days)
    logger.info(f"Starting PIT replay for {main_t} ({source}): {n_days} trading days from {start_date} to {end_date} (full_export={full_export})")

    # 3. Per-day PIT: prefix slice → features (as known *on* day) + news/CA filtered to <= day + optional full scoring/CA
    for i, day in enumerate(trading_days):
        day_str = day.isoformat() if hasattr(day, "isoformat") else str(day)
        try:
            # True point-in-time slice (only bars with Date <= day are visible)
            prefix_prices: dict[str, pd.DataFrame] = {}
            for t, df in prices.items():
                if df is None or df.empty:
                    continue
                pref = df[df.index <= pd.Timestamp(day)].copy()
                if len(pref) >= 20:  # lowered slightly for early ramp + real data density
                    prefix_prices[t] = pref

            if main_t not in prefix_prices:
                continue

            spy_pref = prefix_prices.get("SPY")
            main_df = prefix_prices[main_t]

            # Capture raw OHLCV from the as-of bar (Polygon supplies full bars)
            o = h = l = c = v = None
            try:
                last = main_df.iloc[-1]
                o = float(last.get("Open", last.get("open", 0.0)) or 0.0)
                h = float(last.get("High", last.get("high", 0.0)) or 0.0)
                l = float(last.get("Low", last.get("low", 0.0)) or 0.0)
                c = float(last.get("Close", last.get("close", 0.0)) or 0.0)
                v = float(last.get("Volume", last.get("volume", 0.0)) or 0.0)
            except Exception:
                c = float(main_df["Close"].iloc[-1]) if "Close" in main_df.columns else None

            # PIT features computed on the prefix only — RSI, momentum_pulse, ATR, accel, breadth (on day's slice), etc. will evolve
            try:
                pt_feature_dicts = compute_features_for_universe(
                    prefix_prices, spy_df=spy_pref, config=EngineConfig(as_of=day)
                )
            except Exception as e:
                logger.warning(f"Features failed for {day_str}: {e}")
                pt_feature_dicts = {}

            pt_feats = pt_feature_dicts.get(main_t, {}) or {}

            # News as-of day (filter pre-fetched or synthetic events)
            day_news = []
            for item in news_cache.get(main_t, []):
                try:
                    ts_str = item.get("timestamp") or item.get("published_utc") or item.get("date") or ""
                    ts = pd.to_datetime(ts_str).date() if ts_str else None
                    if ts and ts <= day:
                        day_news.append(item)
                except Exception:
                    continue
            # Always call compute_catalyst_summary (it returns a rich dict with *all* v2.2 keys even for [] / no news,
            # using the documented graceful defaults: primary="Other / Unknown", confidences=0, recency=0, cluster="No articles",
            # source_quality_detail="None", overall_sentiment=None, etc.). This + the explicit promotion below guarantees
            # every requested field is a clean top-level column on *every* row (no missing keys / sparse NaNs in the CSV).
            catalyst = compute_catalyst_summary(day_news or [])

            # CA as-of day (events whose ex/split date <= day); build_context produces relative flags + impact + notes
            full_ca = ca_full.get(main_t, {"dividends": [], "splits": []})
            day_divs = [d for d in full_ca.get("dividends", []) if str(d.get("ex_date", "")) <= day.isoformat()]
            day_spls = [s for s in full_ca.get("splits", []) if str(s.get("split_date", "")) <= day.isoformat()]
            day_ca = {**full_ca, "dividends": day_divs, "splits": day_spls}
            ca_context = build_corporate_action_context(day_ca)

            # Base snapshot (always present, PIT correct)
            snapshot = {
                "date": day,
                "ticker": main_t,
                "data_source": source,
                # Raw price bar as-of the day (Polygon real data or synthetic)
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
                # All PIT features (prefixed for easy filtering / compat with prior light exports)
                **{f"feat_{k}": v for k, v in pt_feats.items()},
            }

            # Exposure Scaling v3 (default 0.0; set in full_export after postprocess)
            snapshot["exposure_scale"] = 0.0
            # v4 calibration
            snapshot["calibration_record"] = {}
            # v4 calibration flattened defaults (populated in full_export or later)
            snapshot["forward_12w_return_pct"] = None
            snapshot["forward_12w_max_dd_pct"] = None
            # v5 RS Acceleration default
            snapshot["feat_rs_acceleration"] = 0.0

            # Catalyst — full v2.2 transparency (all keys the compute returns: strength, primary/secondary+conf, recency, cluster,
            # source_quality_*, sentiment, news_volume_surprise, summary_text, etc.)
            for ck, cv in (catalyst or {}).items():
                if ck == "summary_text":
                    snapshot["catalyst_summary"] = cv
                else:
                    snapshot[ck] = cv
            snapshot["news_count"] = len(day_news)

            # === Explicit promotion of all requested Catalyst Summary v2.2 fields to guaranteed top-level columns ===
            # (backward compatible — existing columns like catalyst_strength_score, catalyst_summary, news_volume_surprise
            # etc. are untouched; these are additive / ensured). Graceful for no-news days.
            cat = catalyst or {}
            snapshot["primary_driver"] = cat.get("primary_driver") or "Other / Unknown"
            snapshot["primary_driver_confidence"] = float(cat.get("primary_driver_confidence") or 0.0)
            snapshot["secondary_driver"] = cat.get("secondary_driver") or ""
            snapshot["secondary_driver_confidence"] = float(cat.get("secondary_driver_confidence") or 0.0)
            snapshot["overall_sentiment"] = cat.get("overall_sentiment") or ""
            snapshot["sentiment_intensity"] = float(cat.get("sentiment_intensity") or 0.0)
            snapshot["recency_score"] = float(cat.get("recency_score") or 0.0)
            snapshot["cluster_score"] = float(cat.get("cluster_score") or 0.0)
            snapshot["cluster_description"] = cat.get("cluster_description") or "No articles"
            snapshot["source_quality_score"] = float(cat.get("source_quality_score") or 0.0)
            snapshot["source_quality_signal"] = cat.get("source_quality_signal") or "low"
            sq_detail = cat.get("source_quality_detail")
            snapshot["source_quality_detail"] = sq_detail if sq_detail is not None else ""
            mrc = cat.get("most_recent_catalyst_utc")
            snapshot["most_recent_catalyst_utc"] = mrc if mrc is not None else ""

            # Corporate Actions — full v1 context flattened (plus the raw object for power users)
            for ck, cv in (ca_context or {}).items():
                if ck == "notes":
                    snapshot["ca_notes"] = " | ".join(cv) if isinstance(cv, (list, tuple)) else str(cv or "")
                else:
                    snapshot[ck] = cv
            # Also expose the full context object (JSON-serializable in to_dict path)
            try:
                import json as _json
                snapshot["corporate_action_context"] = _json.dumps(ca_context) if ca_context else "{}"
            except Exception:
                snapshot["corporate_action_context"] = str(ca_context) if ca_context else ""

            # === Full export: Rocket + abstention (Layer 1) + final_rank via existing scoring/postprocess (PIT) ===
            if full_export:
                # Lazy import only when needed (keeps light imports for callers that only want price+catalyst+CA)
                try:
                    from engine.pipeline.steps.scoring.rocket import compute_rocket_score
                    from engine.pipeline.steps.scoring.scoring_config import ScoringConfig
                    from engine.pipeline.steps.postprocess import postprocess as _postprocess
                except Exception as imp_e:
                    logger.warning(f"Full scoring imports failed (rocket/abstention will be partial): {imp_e}")
                    compute_rocket_score = None
                    ScoringConfig = None
                    _postprocess = None

                rocket_val = 0.0
                if compute_rocket_score is not None:
                    try:
                        scfg = ScoringConfig()
                        rocket_val = float(compute_rocket_score(pt_feats, config=scfg))
                    except Exception as re:
                        logger.debug(f"Rocket compute failed for {day_str}: {re}")

                snapshot["bandits_rocket"] = round(rocket_val, 4)

                # Compute rs_improvement for the "improving RS" part of Catalyst Override (DOCN use case)
                # Positive value means recent relative outperformance vs SPY is better than prior window.
                rs_improvement = 0.0
                try:
                    if len(main_df) > 10 and spy_pref is not None and len(spy_pref) > 10:
                        # recent 5d excess return
                        t_now = main_df["Close"].iloc[-1]
                        t_5 = main_df["Close"].iloc[-6]
                        s_now = spy_pref["Close"].iloc[-1]
                        s_5 = spy_pref["Close"].iloc[-6]
                        recent_excess = (t_now / t_5 - 1) - (s_now / s_5 - 1)
                        # previous 5d window
                        t_10 = main_df["Close"].iloc[-11]
                        s_10 = spy_pref["Close"].iloc[-11]
                        prev_excess = (t_5 / t_10 - 1) - (s_5 / s_10 - 1)
                        rs_improvement = recent_excess - prev_excess
                except Exception:
                    rs_improvement = 0.0

                # Guarantee the requested top-level Rocket / Scoring columns exist for this row
                # (overridden below with real postprocess values when successful).
                snapshot["final_rank"] = 1
                snapshot["rocket_zone"] = None
                snapshot["primary_abstention_reason"] = ""

                # Build a minimal TickerScore for this exact as_of (PIT features + rocket)
                # Then run a 1-element postprocess (with the day's CA) to obtain the full Layer-1 abstention
                # reasoning, final_rank (singleton → 1), enriched notes, rocket_zone, abstention_status etc.
                # This re-uses every bit of the production abstention/CA-enrichment logic without duplication.
                try:
                    if TickerScore is not None and _postprocess is not None:
                        ts = TickerScore(
                            ticker=main_t,
                            as_of=day,
                            close=float(c or 0.0),
                            rsi=float(pt_feats.get("rsi", 50.0)),
                            atr_pct=float(pt_feats.get("atr_pct", 0.0)),
                            adx=float(pt_feats.get("adx", 20.0)),
                            rs_vs_spy=float(pt_feats.get("rs_vs_spy", 0.0)),
                            relative_breadth_score=float(pt_feats.get("relative_breadth_score", 50.0)),
                            raw_expected_range_12w=float(pt_feats.get("raw_expected_range_12w", 0.0) or pt_feats.get("expected_range_12w", 0.0)),
                            raw_expected_range_12m=float(pt_feats.get("raw_expected_range_12m", 0.0) or pt_feats.get("expected_range_12m", 0.0)),
                            short_term_movement_intensity=float(pt_feats.get("short_term_movement_intensity", 0.0)),
                            momentum_pulse=float(pt_feats.get("momentum_pulse", 0.0)),
                            rsi_acceleration=float(pt_feats.get("rsi_acceleration", 0.0)),
                            volatility_expansion_flag=float(pt_feats.get("volatility_expansion_flag", 0.0)),
                            bandits_rocket=rocket_val,
                            final_rank=None,
                            notes="",
                            # Catalyst strength for the override logic (from the day's as-of catalyst computation)
                            catalyst_strength_score=catalyst.get("catalyst_strength_score") if isinstance(catalyst, dict) else None,
                            # v5 RS Acceleration for transitional detection (PIT from prefix)
                            rs_acceleration=pt_feats.get("rs_acceleration", 0.0),
                        )
                        # Attach rs_improvement for the improving-RS condition in override (dynamic attr, defensive)
                        try:
                            ts.rs_improvement = rs_improvement
                        except Exception:
                            pass
                        ca_for_pp = {main_t: day_ca} if day_ca else None
                        pp_rows = _postprocess([ts], config=EngineConfig(as_of=day), corporate_actions=ca_for_pp)
                        if pp_rows:
                            row = pp_rows[0]
                            snapshot["final_rank"] = getattr(row, "final_rank", 1) or 1
                            snapshot["abstention_risk"] = getattr(row, "abstention_risk", "Low")
                            ar = getattr(row, "abstention_reason", "") or ""
                            snapshot["abstention_reason"] = ar
                            snapshot["abstention_status"] = getattr(row, "abstention_status", None)
                            snapshot["rocket_zone"] = getattr(row, "rocket_zone", None)
                            # Lightweight top dominant reason for easy filtering/analysis (top 1 factor)
                            snapshot["primary_abstention_reason"] = ar.split(" + ")[0].strip() if ar else ""
                            # Serialize complex details for clean CSV
                            details = getattr(row, "abstention_details", []) or []
                            try:
                                import json as _json2
                                snapshot["abstention_details"] = _json2.dumps(details, default=str)
                            except Exception:
                                snapshot["abstention_details"] = str(details)
                            snapshot["scorecard_notes"] = getattr(row, "notes", "") or ""
                            # Exposure Scaling v3 (top-level for full_export CSV)
                            snapshot["exposure_scale"] = getattr(row, "exposure_scale", getattr(ts, "exposure_scale", 0.0))
                            # v4 Calibration record (replay-native snapshot)
                            cal = getattr(ts, "calibration_record", None) or getattr(row, "calibration_record", {})
                            snapshot["calibration_record"] = cal
                            # Flattened forward fields (populated later via post-replay script or shift)
                            snapshot["forward_12w_return_pct"] = cal.get("forward_12w_return_pct") if isinstance(cal, dict) else None
                            snapshot["forward_12w_max_dd_pct"] = cal.get("forward_12w_max_dd_pct") if isinstance(cal, dict) else None
                            # v5 RS Acceleration
                            snapshot["feat_rs_acceleration"] = getattr(ts, "rs_acceleration", pt_feats.get("rs_acceleration", 0.0))
                            # Also surface the corporate_action_context from the row if richer
                            if getattr(row, "corporate_action_context", None):
                                try:
                                    snapshot["corporate_action_context"] = _json2.dumps(getattr(row, "corporate_action_context"), default=str)
                                except Exception:
                                    pass
                except Exception as pp_e:
                    logger.warning(f"Postprocess / abstention enrichment failed for {day_str}: {pp_e}")

            snapshots.append(snapshot)

            # Progress + light pacing (real polygon runs benefit from visibility)
            if (i + 1) % 10 == 0 or i == 0 or (i + 1) == n_days:
                rsi_s = pt_feats.get("rsi")
                mom_s = pt_feats.get("momentum_pulse")
                cat_s = catalyst.get("catalyst_strength_score", 0.0) if isinstance(catalyst, dict) else 0.0
                print(f"  [{i+1:3d}/{n_days}] {day_str} close={c:.2f} rsi={rsi_s} mom={mom_s} rocket={snapshot.get('bandits_rocket',0):.2f} cat={cat_s:.3f} news={len(day_news)}")

            if (i + 1) % 30 == 0:
                time.sleep(0.05)

        except Exception as day_err:
            # Never abort the whole replay because of one bad day (rate blip, parse edge, etc.)
            logger.warning(f"Day {day_str} failed (partial row emitted): {day_err}")
            snapshots.append({
                "date": day,
                "ticker": main_t,
                "data_source": source,
                "close": c,
                "error": str(day_err)[:200],
                # Promoted columns (graceful defaults so DF shape stays consistent)
                "primary_driver": "Other / Unknown",
                "primary_driver_confidence": 0.0,
                "secondary_driver": "",
                "secondary_driver_confidence": 0.0,
                "overall_sentiment": "",
                "sentiment_intensity": 0.0,
                "recency_score": 0.0,
                "cluster_score": 0.0,
                "cluster_description": "No articles",
                "source_quality_score": 0.0,
                "source_quality_signal": "low",
                "source_quality_detail": "",
                "most_recent_catalyst_utc": "",
                "bandits_rocket": 0.0,
                "final_rank": None,
                "rocket_zone": None,
                "primary_abstention_reason": "",
                "exposure_scale": 0.0,
                "calibration_record": {},
                "forward_12w_return_pct": None,
                "forward_12w_max_dd_pct": None,
                "feat_rs_acceleration": 0.0,
            })

    df = pd.DataFrame(snapshots)
    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)

    if output_csv:
        p = Path(output_csv)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(p, index=False)
        logger.info(f"Historical replay saved to {p}")

    logger.info(f"Historical daily analysis complete: {len(df)} days for {main_t} ({source}, full_export={full_export}) from {start_date} to {end_date}")
    return df
