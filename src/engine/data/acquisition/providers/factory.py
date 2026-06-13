"""
Phase 5C — Provider Factory

get_provider() decides between real (Polygon) and synthetic based on credential availability
and the prefer_real flag.
"""

from __future__ import annotations

from typing import Optional

from .base import BaseProvider
from .polygon import PolygonProvider
from .synthetic import SyntheticProvider
from ..credential import load_polygon_api_key


def get_provider(prefer_real: bool = True) -> BaseProvider:
    """
    Return the appropriate provider.

    - If prefer_real=True and POLYGON_API_KEY is available → PolygonProvider
    - Otherwise → SyntheticProvider (always works, no external deps)
    """
    if prefer_real:
        key = load_polygon_api_key()
        if key:
            return PolygonProvider(key)

    return SyntheticProvider()
