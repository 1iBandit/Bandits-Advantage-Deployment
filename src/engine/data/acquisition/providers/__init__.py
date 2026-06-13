"""
Phase 5C Providers Package

Exposes the provider classes and factory.
"""

from .base import BaseProvider
from .polygon import PolygonProvider
from .synthetic import SyntheticProvider
from .factory import get_provider

__all__ = [
    "BaseProvider",
    "PolygonProvider",
    "SyntheticProvider",
    "get_provider",
]
