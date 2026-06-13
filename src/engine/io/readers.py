"""
Reference data and price readers for Bandit's Advantage v3 (Phase 2).

This module provides clean, testable functions for loading:
- Ticker universe
- Sector / industry mappings
- Trading holidays
- Corporate actions (placeholder)
- Adjusted OHLCV price history (per-ticker CSV/Parquet files + SPY benchmark)
- Polygon historical daily bars (data_source="polygon" / "polygon_cache")

Design principles:
- All functions accept explicit path arguments for easy testing and configuration.
- Sensible defaults point to a conventional `data/` layout at project root.
- Missing files are handled gracefully (return empty/partial results + clear logging).
- Uses only pandas + pathlib (plus stdlib). No extra deps beyond optional pyarrow for parquet.
- Cache-first for polygon sources; explicit, batched, and defensive (exp backoff + jitter, skip-on-persistent-failure).
- No business logic or scoring — pure data access.

Expected directory layout (relative to project root or CWD):
    data/
        tickers.txt                 # one ticker per line
        sectors.csv                 # columns: ticker,sector
        holidays.txt                # one date per line (YYYY-MM-DD)
        corporate_actions.csv       # placeholder
        prices/
            AAPL.csv (or .parquet)
            MSFT.csv (or .parquet)
            ...
            SPY.csv (or .parquet)

CSV/Parquet price files should contain at minimum:
    Date,Open,High,Low,Close,Volume
Optional: Adj Close (for adjusted prices).

Polygon fetcher (data_source="polygon") creates these on demand using batched requests + resilient retries. "polygon_cache" reads only these (no network).

All price DataFrames are returned with a DatetimeIndex named "Date" and
sorted ascending.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

from dotenv import load_dotenv

# Load .env for POLYGON_API_KEY etc. when this module is used directly
load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths (relative to current working directory when engine runs)
# Users can override by passing explicit paths to each function.
# ---------------------------------------------------------------------------

# Updated defaults to match the recommended organized structure:
# data/
#   reference/
#     tickers.csv
#     holidays.csv
#     mappings/sector_map.csv
#   raw/prices/          ← OHLCV CSVs live here
DEFAULT_DATA_ROOT = Path("data")
DEFAULT_REFERENCE_DIR = DEFAULT_DATA_ROOT / "reference"
DEFAULT_TICKERS_FILE = DEFAULT_REFERENCE_DIR / "tickers.csv"
DEFAULT_SECTORS_FILE = DEFAULT_REFERENCE_DIR / "mappings" / "sector_map.csv"
DEFAULT_HOLIDAYS_FILE = DEFAULT_REFERENCE_DIR / "holidays.csv"
DEFAULT_CORP_ACTIONS_FILE = DEFAULT_REFERENCE_DIR / "corporate_actions.csv"
DEFAULT_PRICES_DIR = DEFAULT_DATA_ROOT / "raw" / "prices"


# ---------------------------------------------------------------------------
# Reference data loaders
# ---------------------------------------------------------------------------

def load_tickers(path: Optional[Path | str] = None) -> List[str]:
    """
    Load the list of tickers to process.

    Supports both simple text files (one ticker per line) and CSV files
    that contain a 'ticker' column (recommended for the new data layout).

    Args:
        path: Path to tickers file (.txt or .csv).
              If None, uses the new default: data/reference/tickers.csv

    Returns:
        Sorted list of uppercase tickers. Empty list if file is missing.
    """
    p = Path(path) if path is not None else DEFAULT_TICKERS_FILE

    if not p.exists():
        logger.warning(f"Ticker file not found: {p}. Returning empty list.")
        return []

    try:
        if p.suffix.lower() == ".csv":
            df = pd.read_csv(p)
            col = next((c for c in df.columns if c.lower() in ("ticker", "symbol", "tickers")), df.columns[0])
            tickers = [str(x).strip().upper() for x in df[col] if pd.notna(x)]
        else:
            # Plain text file support (one per line)
            tickers = [
                line.strip().upper()
                for line in p.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        return sorted(set(tickers))
    except Exception as e:
        logger.warning(f"Failed to parse tickers from {p}: {e}")
        return []


def load_sector_mappings(path: Optional[Path | str] = None) -> Dict[str, str]:
    """
    Load ticker -> sector mapping.

    Args:
        path: Path to CSV with at least columns 'ticker' and 'sector'.
              If None, uses the new default: data/reference/mappings/sector_map.csv

    Returns:
        Dictionary {TICKER: sector}. Empty dict if file missing or unreadable.
    """
    p = Path(path) if path is not None else DEFAULT_SECTORS_FILE

    if not p.exists():
        logger.warning(f"Sector mappings file not found: {p}. Returning empty dict.")
        return {}

    try:
        df = pd.read_csv(p)
        # Be flexible with column names
        ticker_col = next((c for c in df.columns if c.lower() in ("ticker", "symbol")), df.columns[0])
        sector_col = next((c for c in df.columns if c.lower() in ("sector", "industry")), df.columns[1] if len(df.columns) > 1 else df.columns[0])

        mapping = {
            str(row[ticker_col]).strip().upper(): str(row[sector_col]).strip()
            for _, row in df.iterrows()
            if pd.notna(row[ticker_col])
        }
        return mapping
    except Exception as e:
        logger.warning(f"Failed to read sector mappings from {p}: {e}")
        return {}


def load_holidays(path: Optional[Path | str] = None) -> Set[str]:
    """
    Load trading holidays as ISO date strings.

    Args:
        path: Path to a text or CSV file with dates.
              If None, uses the new default: data/reference/holidays.csv

    Returns:
        Set of date strings. Empty set if file is missing.
    """
    p = Path(path) if path is not None else DEFAULT_HOLIDAYS_FILE

    if not p.exists():
        logger.warning(f"Holidays file not found: {p}. Returning empty set.")
        return set()

    holidays: Set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            # Basic validation / normalization
            try:
                # Accept YYYY-MM-DD or other parseable formats
                dt = pd.to_datetime(line).date()
                holidays.add(dt.isoformat())
            except Exception:
                logger.debug(f"Skipping unparseable holiday line: {line}")
    return holidays


def load_corporate_actions(path: Optional[Path | str] = None) -> pd.DataFrame:
    """
    Load corporate actions (dividends, splits, etc.).

    This is currently a placeholder that returns an empty DataFrame with
    the expected schema. Real implementation will parse a corporate actions
    file or database when available.

    Args:
        path: Path to corporate actions CSV (ignored in Phase 2 placeholder).

    Returns:
        Empty pandas DataFrame with columns:
        ['ticker', 'date', 'action_type', 'value', 'adjustment_factor']
    """
    p = Path(path) if path is not None else DEFAULT_CORP_ACTIONS_FILE

    if not p.exists():
        logger.info(f"Corporate actions file not found (placeholder): {p}")

    # Always return a typed empty frame so callers have a stable schema
    return pd.DataFrame(
        columns=["ticker", "date", "action_type", "value", "adjustment_factor"]
    ).astype(
        {
            "ticker": "string",
            "date": "string",
            "action_type": "string",
            "value": "float64",
            "adjustment_factor": "float64",
        }
    )


# ---------------------------------------------------------------------------
# Internal price helpers (shared by loaders + polygon fetcher)
# ---------------------------------------------------------------------------

def _normalize_ohlcv_df(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """
    Normalize a raw price DataFrame to the engine's expected shape:
    - DatetimeIndex named "Date"
    - Columns: Open, High, Low, Close, Volume (float)
    Returns None on unrecoverable issues (with logging).
    """
    if df is None or len(df) == 0:
        return None
    try:
        # Normalize column names
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

        # Ensure Date column
        if "date" not in df.columns:
            logger.warning(f"No 'Date' column in {ticker} prices during normalize.")
            return None

        df = df.rename(columns={"date": "Date"}).set_index("Date")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df.index.name = "Date"

        # Flexible column mapping
        col_map = {}
        for want, candidates in {
            "Open": ["open", "o"],
            "High": ["high", "h"],
            "Low": ["low", "l"],
            "Close": ["close", "c", "adj_close", "adjclose", "adjusted_close"],
            "Volume": ["volume", "vol", "v"],
        }.items():
            for cand in candidates:
                if cand in df.columns:
                    col_map[cand] = want
                    break

        df = df.rename(columns=col_map)

        # Ensure required columns exist
        final_cols = ["Open", "High", "Low", "Close", "Volume"]
        for col in final_cols:
            if col not in df.columns:
                df[col] = pd.NA

        df = df[final_cols].astype(float)
        return df
    except Exception as e:
        logger.warning(f"Failed to normalize OHLCV for {ticker}: {e}")
        return None


def _load_single_ohlcv(ticker: str, root: Path) -> Optional[pd.DataFrame]:
    """
    Load a single ticker's price file (parquet preferred, then csv) and normalize.
    Returns None if file missing or unreadable (no warning here; caller decides).
    """
    t = ticker.upper()
    csv_path = root / f"{t}.csv"
    parquet_path = root / f"{t}.parquet"

    df: Optional[pd.DataFrame] = None

    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
        except Exception as e:
            logger.warning(f"Failed to read Parquet for {t} at {parquet_path}: {e}")
            df = None
    if df is None and csv_path.exists():
        try:
            df = pd.read_csv(csv_path, parse_dates=["Date"])
        except Exception as e:
            logger.warning(f"Failed to read CSV for {t} at {csv_path}: {e}")
            df = None

    if df is None:
        return None

    return _normalize_ohlcv_df(df, t)


def _save_ohlcv_to_cache(ticker: str, df: pd.DataFrame, root: Path) -> bool:
    """
    Save a normalized price DF to the cache dir.
    Prefers .parquet (if pyarrow or other engine works), falls back to .csv.
    Creates the dir if needed.
    """
    root.mkdir(parents=True, exist_ok=True)
    t = ticker.upper()

    # Try parquet first
    try:
        p = root / f"{t}.parquet"
        df.to_parquet(p, index=True)
        return True
    except Exception as e:
        logger.debug(f"Parquet write failed for {t} (pyarrow/fastparquet may be missing): {e}")

    # Fallback to CSV (compatible with existing loader)
    try:
        p = root / f"{t}.csv"
        df_out = df.reset_index()  # write Date as column for easy csv roundtrips
        df_out.to_csv(p, index=False)
        return True
    except Exception as e:
        logger.warning(f"Failed to write cache file for {t}: {e}")
        return False


def _fetch_polygon_aggs(
    ticker: str,
    from_str: str,
    to_str: str,
    api_key: str,
    max_retries: int = 4,
    base_backoff: float = 1.5,
    max_backoff: float = 60.0,
) -> tuple[list[dict], bool]:
    """
    Internal: fetch daily aggregates for ONE ticker from Polygon (with resilience).
    Uses exponential backoff + jitter on transient/429 errors.
    Respects 'Retry-After' header when provided by Polygon.
    Returns (results_list, hit_rate_limit) so caller can track for summary.
    Never raises; returns ([], hit) on persistent failure after max_retries.
    """
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{from_str}/{to_str}"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={api_key}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "BanditsAdvantage/1.0"})

    hit_rate_limit = False
    last_err = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
            status = data.get("status")
            if status not in ("OK", "DELAYED"):
                logger.warning(f"Polygon aggs for {ticker} returned status: {status}")
                return [], hit_rate_limit
            if status == "DELAYED":
                logger.info(f"Polygon returned DELAYED status for {ticker} (free tier / delayed data) - using results anyway.")
            return data.get("results", []) or [], hit_rate_limit
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                hit_rate_limit = True
                # Respect Retry-After if present
                retry_after = None
                if hasattr(e, "headers") and e.headers:
                    retry_after = e.headers.get("Retry-After")
                if retry_after:
                    sleep_s = float(retry_after)
                else:
                    sleep_s = min(base_backoff * (2 ** attempt) + random.uniform(0.0, 1.5), max_backoff)
                logger.warning(f"Polygon rate limit (429) for {ticker} (attempt {attempt+1}/{max_retries}), backing off {sleep_s:.1f}s (jitter)")
                time.sleep(sleep_s)
                continue
            else:
                logger.warning(f"HTTP error fetching Polygon aggs for {ticker} {from_str}-{to_str}: {e}")
                # non-429 HTTP errors usually not worth full retry storm
                break
        except urllib.error.URLError as e:
            last_err = e
            if attempt < max_retries - 1:
                sleep_s = min(base_backoff * (2 ** attempt) + random.uniform(0.0, 1.0), max_backoff)
                logger.warning(f"Network error for {ticker} (attempt {attempt+1}), retry in {sleep_s:.1f}s: {e}")
                time.sleep(sleep_s)
                continue
            break
        except json.JSONDecodeError as e:
            last_err = e
            logger.warning(f"Failed to parse Polygon aggs response for {ticker}: {e}")
            break
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                sleep_s = min(1.0 + random.uniform(0, 0.5), 5.0)
                time.sleep(sleep_s)
                continue
            break
    logger.warning(f"Failed to fetch Polygon aggs for {ticker} after {max_retries} attempts. Last error: {last_err}")
    return [], hit_rate_limit


def _polygon_results_to_df(results: list[dict], ticker: str) -> Optional[pd.DataFrame]:
    """Convert Polygon aggs 'results' list into normalized OHLCV DataFrame."""
    if not results:
        return None
    try:
        df = pd.DataFrame(results)
        # 't' = timestamp in ms
        df["Date"] = pd.to_datetime(df["t"], unit="ms")
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df = df.set_index("Date")
        df = df.sort_index()
        df.index.name = "Date"
        # ensure types
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                df[col] = pd.NA
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.astype(float)
    except Exception as e:
        logger.warning(f"Failed to convert Polygon results to DF for {ticker}: {e}")
        return None


# Public fetcher (the main entry point for data_source="polygon" / "polygon_cache")
def fetch_polygon_ohlcv(
    tickers: List[str],
    prices_dir: Optional[Path | str] = None,
    benchmark: str = "SPY",
    lookback_days: int = 400,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    api_key: Optional[str] = None,
    # Phase 5.1 stability controls
    batch_size: int = 15,
    batch_pause_seconds: float = 2.0,
    max_retries: int = 4,
    cache_only: bool = False,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch daily OHLCV history from Polygon.io (cache-first, batched, resilient).

    Batch processing + exponential backoff with jitter helps survive rate limits
    when fetching 40-100+ tickers.

    - cache_only=True (used for data_source="polygon_cache"): ONLY reads from local
      parquet/csv cache using the same sufficiency checks. Raises clear RuntimeError
      listing any missing tickers. **Guarantees zero Polygon API calls**.
    - Normal mode (data_source="polygon"): cache-first per ticker; if insufficient,
      fetch using batched requests + per-ticker retries with exp backoff+jitter.
      On persistent failure for a ticker, log and continue (skip-and-continue).
    - Always includes benchmark (SPY).
    - 400d lookback default.
    - Returns partial results on errors (never aborts whole run for one bad ticker).
    - At end logs a clear summary + batch progress.

    The returned dict shape matches load_ohlcv_prices.

    Callers (ingest, legacy) should pass the cfg.* values for batch/retry settings.
    """
    root = Path(prices_dir) if prices_dir is not None else DEFAULT_PRICES_DIR
    root.mkdir(parents=True, exist_ok=True)

    if api_key is None:
        api_key = os.getenv("POLYGON_API_KEY")

    all_tickers = list(dict.fromkeys([*tickers, benchmark]))

    # Resolve date window (calendar days)
    if to_date is None:
        to_date = date.today()
    if from_date is None:
        from_date = to_date - timedelta(days=lookback_days)
    from_str = from_date.strftime("%Y-%m-%d")
    to_str = to_date.strftime("%Y-%m-%d")

    prices: Dict[str, pd.DataFrame] = {}

    if cache_only:
        logger.info("polygon_cache mode active: using ONLY local cache (no API calls will be made)")
        missing = []
        for tkr in all_tickers:
            t = tkr.upper()
            cached = _load_single_ohlcv(t, root)
            if cached is not None:
                min_date_ok = cached.index.min().date() <= from_date
                enough_rows = len(cached) >= max(1, int(lookback_days * 0.3))
                if min_date_ok and enough_rows:
                    prices[t] = cached
                    continue
            missing.append(t)
        if missing:
            raise RuntimeError(
                f"data_source='polygon_cache' is strict: cached data missing or insufficient for {missing}. "
                "First run with data_source='polygon' (needs POLYGON_API_KEY) to populate cache, "
                "or manually place the .parquet/.csv files in the prices directory."
            )
        logger.info(f"polygon_cache complete: {len(prices)} tickers loaded from cache (0 API calls).")
        return prices

    # === Normal "polygon" mode: batched fetch with resilience ===
    successes = 0
    skipped_tickers: list[str] = []
    rate_limited_tickers: list[str] = []

    n = len(all_tickers)
    effective_batch = max(1, int(batch_size))
    n_batches = (n + effective_batch - 1) // effective_batch

    for b_idx in range(0, n, effective_batch):
        batch = all_tickers[b_idx : b_idx + effective_batch]
        batch_num = (b_idx // effective_batch) + 1
        logger.info(f"Polygon batch {batch_num}/{n_batches} ({len(batch)} tickers) starting: {[x.upper() for x in batch[:4]]}{'...' if len(batch)>4 else ''}")

        for tkr in batch:
            t = tkr.upper()

            # Cache-first with sufficiency
            cached = _load_single_ohlcv(t, root)
            if cached is not None:
                min_date_ok = cached.index.min().date() <= from_date
                enough_rows = len(cached) >= max(1, int(lookback_days * 0.3))
                if min_date_ok and enough_rows:
                    prices[t] = cached
                    successes += 1
                    continue
                else:
                    logger.info(f"Cached {t} (len={len(cached)}) insufficient for requested window; will re-fetch.")

            if not api_key:
                logger.warning(f"POLYGON_API_KEY not set; cannot fetch {t}. Skipping.")
                skipped_tickers.append(t)
                continue

            logger.info(f"  Fetching {t} ({from_str}..{to_str})...")
            results, hit_rl = _fetch_polygon_aggs(
                t, from_str, to_str, api_key, max_retries=max_retries
            )
            if hit_rl:
                rate_limited_tickers.append(t)

            df = _polygon_results_to_df(results, t)
            if df is None or len(df) == 0:
                logger.warning(f"No usable data returned for {t} after retries. Skipping.")
                skipped_tickers.append(t)
                continue

            _save_ohlcv_to_cache(t, df, root)
            prices[t] = df
            successes += 1

        # inter-batch pause (rate limit courtesy)
        if b_idx + effective_batch < n:
            logger.debug(f"Pausing {batch_pause_seconds:.1f}s between Polygon batches...")
            time.sleep(batch_pause_seconds)

    # Ensure benchmark visibility
    b = benchmark.upper()
    if b not in prices and any(x.upper() == b for x in all_tickers):
        logger.warning(f"Benchmark {b} could not be obtained (cache or fetch).")

    # Final observability summary
    total = len(all_tickers)
    logger.info(
        f"Polygon fetch complete: {successes} succeeded, {len(skipped_tickers)} skipped after retries, "
        f"{len(rate_limited_tickers)} hit rate limits (batch_size={effective_batch}, max_retries={max_retries}). "
        f"From {total} requested tickers."
    )
    if skipped_tickers:
        shown = skipped_tickers[:8]
        logger.info(f"  Skipped tickers (first {len(shown)}): {shown}{'...' if len(skipped_tickers) > 8 else ''}")
    if rate_limited_tickers:
        shown = rate_limited_tickers[:8]
        logger.info(f"  Rate-limited tickers (first {len(shown)}): {shown}{'...' if len(rate_limited_tickers) > 8 else ''}")

    return prices


# ---------------------------------------------------------------------------
# Price data loader
# ---------------------------------------------------------------------------

def load_ohlcv_prices(
    tickers: List[str],
    prices_dir: Optional[Path | str] = None,
    benchmark: str = "SPY",
) -> Dict[str, pd.DataFrame]:
    """
    Load adjusted daily OHLCV price history for the requested tickers plus benchmark.

    Each ticker is expected to have its own CSV file:
        {prices_dir}/{TICKER}.csv

    Expected columns (case-insensitive, flexible):
        Date, Open, High, Low, Close, Volume
    Optional:
        Adj Close (will be used preferentially as 'Close' if present for adjusted series)

    Args:
        tickers: List of tickers to load (benchmark is added automatically if not present).
        prices_dir: Directory containing the per-ticker CSV files.
                    Defaults to data/prices/.
        benchmark: Benchmark ticker to ensure is always loaded (default "SPY").

    Returns:
        Dictionary mapping uppercase ticker -> price DataFrame.
        DataFrames have:
            - DatetimeIndex named "Date"
            - Columns: Open, High, Low, Close, Volume (all float)
        Tickers whose files are missing are omitted (with a warning).
    """
    root = Path(prices_dir) if prices_dir is not None else DEFAULT_PRICES_DIR
    all_tickers = list(dict.fromkeys([*tickers, benchmark]))  # preserve order, unique

    prices: Dict[str, pd.DataFrame] = {}

    if not root.exists():
        logger.warning(f"Prices directory does not exist: {root}. No price data loaded.")
        return prices

    for ticker in all_tickers:
        df = _load_single_ohlcv(ticker, root)
        if df is None:
            t = ticker.upper()
            logger.warning(f"Price file not found for {t} (looked in {root}). Skipping.")
            continue
        prices[ticker.upper()] = df

    return prices
