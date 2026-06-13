"""
Ingest step (Phase 2).

Loads ticker universe, reference data, and price history (OHLCV).
Returns a structured dict that downstream steps (especially features) consume.

Phase 2: Data loading. Respects config.data_source:
- "synthetic": generates fresh synthetic OHLCV for the exact requested tickers + SPY
  (using cfg.synthetic_days / synthetic_seed).
- "real" / "csv_dir" / "csv": loads from disk via io readers (data/raw/prices by default).
  Missing tickers are skipped (with warning); only successfully loaded ones are kept.
- "polygon": cache-first fetch via Polygon (if no local cache file for a ticker, fetch + save
  to data/raw/prices/*.parquet or .csv). Always includes SPY. Uses ~400d window.
- "polygon_cache": strict cache-only read from data/raw/prices/. Fails loudly if any requested
  ticker (incl. SPY) is missing its cached file. No API calls.

Uses readers from engine.io.readers for ticker lists, sector mappings, holidays, etc.
Missing data files are handled gracefully (warnings logged, partial results returned) except
for "polygon_cache" which is intentionally strict.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict

from engine.io import readers
from engine.models.core import EngineConfig

# Live corporate actions (MASSIVE-backed, v1 integration)
try:
    from engine.pipeline.steps.corporate_actions import batch_get_corporate_actions as _batch_ca
except Exception:
    _batch_ca = None


def ingest(config: EngineConfig | None = None) -> Dict[str, Any]:
    """
    Main ingest entry point.

    Returns:
        {
            "config": EngineConfig,
            "tickers": list[str],
            "prices": dict[str, pd.DataFrame],   # ticker -> OHLCV DataFrame (incl. SPY)
            "spy": pd.DataFrame | None,
            "ref_data": dict,                     # sector mappings etc.
            "holidays": set[str],
            "corporate_actions": dict[str, dict],   # rich per-ticker from live module (v1)
            "corporate_actions_df": pd.DataFrame,   # legacy stub for compat
            "as_of": date,
        }
    """
    cfg = config or EngineConfig()
    if cfg.as_of is None:
        cfg.as_of = date.today()

    # --- Universe resolution ---
    # Prefer the effective universe that was resolved by build_universe (run_engine)
    # or fall back to direct ticker_universe / load_tickers for direct ingest calls.
    # Support both the new `tickers` (ad-hoc) and legacy `ticker_universe` fields.
    if getattr(cfg, "tickers", None):
        tickers = [t.upper() for t in cfg.tickers]
    elif cfg.ticker_universe:
        tickers = [t.upper() for t in cfg.ticker_universe]
    else:
        tickers = readers.load_tickers(getattr(cfg, "core_universe_path", None))

    # --- Reference data via the new io readers ---
    sector_map = readers.load_sector_mappings()
    holidays = readers.load_holidays()
    corp_actions = readers.load_corporate_actions()

    # --- Price history (adjusted OHLCV) ---
    # Respect config.data_source:
    # - "synthetic": always generate fresh synthetic data for the requested tickers + SPY
    # - "real" / "csv_dir" / "csv": load from disk (missing tickers skipped with warning)
    # - "polygon": fetch from Polygon (cache-first + batched + exp backoff+jitter + skip-on-fail) + persist
    # - "polygon_cache": ONLY local cache (no API); raises clear error listing missing tickers (fail-fast)
    source = (getattr(cfg, "data_source", "synthetic") or "synthetic").lower()
    if source == "synthetic":
        from engine.data.readers import generate_synthetic_ohlcv
        all_tickers = list(dict.fromkeys([*tickers, "SPY"]))
        n_days = getattr(cfg, "synthetic_days", 400) or 400
        seed = getattr(cfg, "synthetic_seed", 42) or 42
        prices = generate_synthetic_ohlcv(all_tickers, n_days=n_days, seed=seed)
    elif source == "polygon":
        prices_dir = getattr(cfg, "data_path", None) or "data/raw/prices"
        lookback = getattr(cfg, "synthetic_days", 400) or 400
        prices = readers.fetch_polygon_ohlcv(
            tickers,
            prices_dir=prices_dir,
            benchmark="SPY",
            lookback_days=lookback,
            batch_size=getattr(cfg, "polygon_batch_size", 15),
            batch_pause_seconds=getattr(cfg, "polygon_batch_pause_seconds", 2.0),
            max_retries=getattr(cfg, "polygon_max_retries", 4),
            cache_only=False,
        )
    elif source == "polygon_cache":
        prices_dir = getattr(cfg, "data_path", None) or "data/raw/prices"
        lookback = getattr(cfg, "synthetic_days", 400) or 400
        # Use fetch with cache_only=True: this guarantees no API calls + unified sufficiency checks + clear error
        prices = readers.fetch_polygon_ohlcv(
            tickers,
            prices_dir=prices_dir,
            benchmark="SPY",
            lookback_days=lookback,
            batch_size=getattr(cfg, "polygon_batch_size", 15),
            batch_pause_seconds=getattr(cfg, "polygon_batch_pause_seconds", 2.0),
            max_retries=getattr(cfg, "polygon_max_retries", 4),
            cache_only=True,
        )
    else:
        # real data from configured or default directory (original behavior)
        prices_dir = getattr(cfg, "data_path", None) or "data/raw/prices"
        prices = readers.load_ohlcv_prices(tickers, prices_dir=prices_dir, benchmark="SPY")

    # Extract SPY if it was successfully loaded
    spy = prices.get("SPY")

    # Basic ref_data bundle for downstream consumers
    ref_data = {
        "sectors": sector_map,
        # Future: add more reference tables here
    }

    # --- Corporate actions (live via MASSIVE module if available, else stub) ---
    # Return rich per-ticker dict for context building (preferred for v1 integration).
    # The old io stub DF is still called for backward compat in the return under "corporate_actions_df".
    if _batch_ca is not None:
        try:
            ca_dict = _batch_ca(
                tickers,
                pause_seconds=1.5,
                dividend_lookback_days=365 * 3,
                split_lookback_days=365 * 5,
            )
        except Exception:
            ca_dict = {}
    else:
        ca_dict = {}

    # Keep the legacy stub DF under a different key so existing (minimal) callers don't break immediately
    corp_actions_df = corp_actions  # the placeholder from io

    return {
        "config": cfg,
        "tickers": tickers,
        "prices": prices,
        "spy": spy,
        "ref_data": ref_data,
        "holidays": holidays,
        "corporate_actions": ca_dict,          # rich dict[ticker] -> context-ready (v1 preferred)
        "corporate_actions_df": corp_actions_df,  # legacy placeholder DF
        "as_of": cfg.as_of,
    }
