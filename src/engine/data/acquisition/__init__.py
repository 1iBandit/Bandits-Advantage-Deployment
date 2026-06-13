"""
Phase 5A — Data Acquisition Layer (v0.1)

Isolated module for ad-hoc pulls, nightly orchestration, and dynamic universe expansion.

All logic is strictly a service layer:
- No scoring
- No feature engineering
- No decision logic
- No leakage into narrative.py, analyst_workbench.py, or Phase 4L presenters

See Phase5A_Data_Acquisition_Contract_v0.1.md for full contract.
"""

from .manifest import create_run_manifest
from .pull import pull_symbol
from .universe import get_dynamic_universe, update_nightly_run_list, get_current_nightly_symbols
from .nightly import run_nightly_acquisition
from .adapters import get_price_reader_for_symbol, build_snapshot_from_acquisition
from .credential import load_polygon_api_key
from .providers import BaseProvider, PolygonProvider, SyntheticProvider, get_provider
from .rate_limit import handle_rate_limit

__all__ = [
    "create_run_manifest",
    "pull_symbol",
    "get_dynamic_universe",
    "update_nightly_run_list",
    "get_current_nightly_symbols",
    "run_nightly_acquisition",
    "get_price_reader_for_symbol",
    "build_snapshot_from_acquisition",
    "load_polygon_api_key",
    "BaseProvider",
    "PolygonProvider",
    "SyntheticProvider",
    "get_provider",
    "handle_rate_limit",
]