"""
Phase 5C — Credential Loader

Securely loads Polygon API key from environment or .env file.
Never logs the key. Returns None if unavailable (triggers synthetic fallback).
"""

from __future__ import annotations

from typing import Optional
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional; env vars still work


def load_polygon_api_key() -> Optional[str]:
    """
    Load POLYGON_API_KEY from environment (preferred) or .env.
    Returns None if not present (safe for synthetic fallback).
    """
    key = os.getenv("POLYGON_API_KEY")
    if key:
        return key.strip()
    return None
