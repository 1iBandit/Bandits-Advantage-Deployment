"""News-related readers and providers (Phase 3+ foundation).

This package contains stand-alone news functionality (not integrated into scoring).

Exports:
- fetch_news (from news_reader) - fetches and normalizes MASSIVE news (core 4 keys + rich fields)
- compute_catalyst_summary (from catalyst_summary) - rule-based catalyst summary (v2.2: fallbacks for Other/Unknown + secondary conf*0.88)
- get_news_provider
"""

from .news_reader import fetch_news, get_news_provider
from .catalyst_summary import compute_catalyst_summary

__all__ = ["fetch_news", "get_news_provider", "compute_catalyst_summary"]
