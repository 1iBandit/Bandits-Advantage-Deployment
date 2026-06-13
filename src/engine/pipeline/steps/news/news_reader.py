"""
News Reader Module (MASSIVE minimal skeleton)

Provides fetch_news() for the NewsPulse layer.

- Loads MASSIVE_API_KEY via dotenv + os.getenv (consistent with universe.py pattern).
- Placeholder URL builder (endpoint shape will be refined when real MASSIVE
  integration details are known).
- Uses stdlib urllib (no extra deps) with headers, timeout, and defensive errors.
- Always returns a normalized list of dicts.
  - Core 4 keys (backward compatible for existing NewsPulse / compute_news_pulse):
    [{"headline": str, "timestamp": str, "source": str, "summary": str}, ...]
  - Richer fields are also included when available from MASSIVE TickerNews
    (id, url, author, description, keywords, tickers, publisher, sentiment,
     sentiment_reasoning, insights, etc.). Old code ignoring extra keys continues
     to work unchanged.

The implementation is intentionally minimal and mockable (patch the private
_fetch_massive_news helper for unit tests).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any

from dotenv import load_dotenv

# Ensure .env is loaded when news_reader.py is used directly (e.g. in tests or scripts)
load_dotenv()

# Use official MASSIVE client when available (preferred over placeholder urllib)
try:
    from massive import RESTClient
    from massive.rest.models import TickerNews
except ImportError:
    RESTClient = None
    TickerNews = None

logger = logging.getLogger(__name__)


def fetch_news(ticker: str, as_of: date | None = None) -> list[dict[str, Any]]:
    """
    Fetch news items for a given ticker.

    Uses the MASSIVE news API when MASSIVE_API_KEY is present.
    Returns a normalized list of dicts (see module docstring for shape).

    If the API key is missing or any network/parse error occurs, returns [] defensively.

    Args:
        ticker: The ticker symbol (e.g., "AAPL").
        as_of: Optional reference date for the news query (used to scope recency).

    Returns:
        List of normalized news items.
        Each item has the core 4 keys (for backward compat) plus richer fields
        (id, url, publisher, tickers, sentiment, etc.) when present in the source data.
        Example core shape:
            [{"headline": "...", "timestamp": "...", "source": "...", "summary": "..."}, ...]
    """
    api_key = os.getenv("MASSIVE_API_KEY")
    if not api_key:
        logger.warning("MASSIVE_API_KEY not set. News fetch disabled (returning empty list).")
        return []

    try:
        return _fetch_massive_news(ticker, api_key, as_of)
    except Exception as e:
        logger.debug(f"Unexpected failure in fetch_news for {ticker}: {e}")
        return []


def get_news_provider() -> str:
    """
    Returns the configured news provider.

    For now this is hardcoded to 'massive' as a placeholder.
    In the future this could read from EngineConfig.news_provider.
    """
    return "massive"


# =============================================================================
# Internal helpers
# (old _build_massive_news_url removed after migration to official massive client)
# =============================================================================


def _fetch_massive_news(
    ticker: str, api_key: str, as_of: date | None = None
) -> list[dict[str, Any]]:
    """
    Fetch recent news for a ticker using the official MASSIVE Python client.

    Defensive: returns [] on import issues, auth, rate limits, or any error.
    Normalizes to the stable 4-key dicts expected by compute_news_pulse.

    Easy to mock:
        with patch(...) as mock:
            mock.return_value = [{"headline": "...", ...}]
    """
    if RESTClient is None:
        logger.debug("massive package not installed; falling back to empty news.")
        return []

    try:
        client = RESTClient(api_key)
        items = []
        # Fetch a few recent items for the ticker
        kwargs = {}
        if as_of:
            kwargs["published_utc_lte"] = as_of.isoformat() if hasattr(as_of, 'isoformat') else str(as_of)
        for n in client.list_ticker_news(
            ticker=ticker.upper(),
            limit=5,
            sort="published_utc",
            order="desc",
            **kwargs,
        ):
            if isinstance(n, TickerNews):
                items.append(n)
            if len(items) >= 5:
                break
        # Convert first few to our canonical shape (use the project's normalizer on raw dicts)
        raw_list = []
        for item in items:
            # TickerNews has attributes; convert to dict-like for normalizer
            d = item.__dict__ if hasattr(item, "__dict__") else {}
            raw_list.append(d)
        return _normalize_to_canonical_news(raw_list)
    except Exception as e:
        logger.debug(f"News fetch (MASSIVE client) issue for {ticker}: {e}")
        return []


def _normalize_to_canonical_news(data: Any) -> list[dict[str, Any]]:
    """
    Map MASSIVE TickerNews (or raw response) into a backward-compatible canonical shape.

    Always includes the original 4 keys for existing consumers (NewsPulse, etc.):
        "headline", "timestamp", "source", "summary"

    Additionally includes richer fields when present from the MASSIVE TickerNews model:
        "id", "url", "author", "description", "image_url", "keywords", "tickers",
        "publisher" (dict with name etc.), "sentiment", "sentiment_reasoning",
        "insights" (raw if available)

    This keeps fetch_news() returning the original 4-key shape (extra keys are
    transparent to old code) while enabling the new Catalyst Summary layer.

    Handles both raw dicts and objects with __dict__.
    """
    if not data:
        return []

    # Unwrap common response envelopes (for raw API fallback)
    items: list[dict] = []
    if isinstance(data, dict):
        for key in ("news", "articles", "results", "data", "items", "headlines"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        if not items:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        items = [data]

    normalized: list[dict[str, Any]] = []
    for raw_item in items:
        if raw_item is None:
            continue

        # Normalize to dict (handle TickerNews objects or dicts from __dict__)
        if not isinstance(raw_item, dict):
            if hasattr(raw_item, "__dict__"):
                raw_item = raw_item.__dict__.copy()
            else:
                continue

        # Core 4 keys (backward compat)
        headline = (
            raw_item.get("headline")
            or raw_item.get("title")
            or raw_item.get("head")
            or (str(raw_item.get("summary", ""))[:100] if raw_item.get("summary") else "")
            or ""
        )
        timestamp = (
            raw_item.get("timestamp")
            or raw_item.get("published_at")
            or raw_item.get("published")
            or raw_item.get("published_utc")
            or raw_item.get("date")
            or raw_item.get("time")
            or ""
        )
        source = raw_item.get("source") or raw_item.get("provider") or raw_item.get("feed") or "massive"
        summary = raw_item.get("summary") or raw_item.get("description") or raw_item.get("body") or raw_item.get("text") or ""

        # Richer fields
        item_id = raw_item.get("id") or ""
        url = raw_item.get("article_url") or raw_item.get("amp_url") or ""
        author = raw_item.get("author") or ""
        description = raw_item.get("description") or summary
        image_url = raw_item.get("image_url") or ""

        keywords = raw_item.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        keywords = [str(k) for k in keywords]

        tickers = raw_item.get("tickers") or []
        if isinstance(tickers, str):
            tickers = [tickers]
        tickers = [str(t) for t in tickers]

        # Publisher
        pub = raw_item.get("publisher")
        if isinstance(pub, dict):
            publisher = {
                "name": pub.get("name", source),
                "homepage_url": pub.get("homepage_url"),
                "logo_url": pub.get("logo_url"),
                "favicon_url": pub.get("favicon_url"),
            }
            publisher = {k: v for k, v in publisher.items() if v is not None}
        elif hasattr(pub, "name"):
            publisher = {"name": getattr(pub, "name", source)}
            for attr in ("homepage_url", "logo_url", "favicon_url"):
                val = getattr(pub, attr, None)
                if val:
                    publisher[attr] = val
        else:
            publisher = {"name": str(pub) if pub else source}

        # Sentiment from insights (list of Insight or dict)
        sentiment = None
        sentiment_reasoning = None
        insights_raw = raw_item.get("insights") or []
        if isinstance(insights_raw, list) and insights_raw:
            for ins in insights_raw:
                if isinstance(ins, dict):
                    s = ins.get("sentiment")
                    if s:
                        sentiment = str(s).lower()
                        sentiment_reasoning = ins.get("sentiment_reasoning")
                        break
                else:
                    s = getattr(ins, "sentiment", None)
                    if s:
                        sentiment = str(s).lower()
                        sentiment_reasoning = getattr(ins, "sentiment_reasoning", None)
                        break

        normalized.append(
            {
                # Original 4 (required for compat)
                "headline": str(headline),
                "timestamp": str(timestamp),
                "source": str(source),
                "summary": str(summary),
                # Richer fields (for catalyst summary etc.)
                "id": str(item_id),
                "url": str(url),
                "author": str(author),
                "description": str(description),
                "image_url": str(image_url),
                "keywords": keywords,
                "tickers": tickers,
                "publisher": publisher,
                "sentiment": sentiment,
                "sentiment_reasoning": str(sentiment_reasoning) if sentiment_reasoning else None,
                "insights": insights_raw if isinstance(insights_raw, list) else [],
            }
        )

    return normalized
