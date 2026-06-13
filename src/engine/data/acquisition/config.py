"""
Phase 5A — Acquisition Configuration (v0.1)

Central place for thresholds, defaults, and source configuration.
This file is intentionally small in v0.1; it will grow as real data providers
and more sophisticated expansion rules are added.
"""

from __future__ import annotations

from typing import Dict, Any

# Volume thresholds used by dynamic universe expansion (v0.1 defaults)
DEFAULT_VOLUME_THRESHOLDS: Dict[str, Any] = {
    "top_equities": 300,
    "top_etfs": 200,
    "min_avg_volume": 500_000,   # shares
}

# Default data source for v0.1 (will be replaced by real provider config)
DEFAULT_SOURCE = "synthetic"

# How many days of history we consider "sufficient" for a new symbol
# to be usable by downstream scoring/narrative layers (v0.1 guidance value)
MIN_HISTORY_DAYS_FOR_NEW_SYMBOL = 60


def get_acquisition_config() -> Dict[str, Any]:
    """Return the current acquisition configuration as a plain dict."""
    return {
        "volume_thresholds": DEFAULT_VOLUME_THRESHOLDS.copy(),
        "default_source": DEFAULT_SOURCE,
        "min_history_days_for_new_symbol": MIN_HISTORY_DAYS_FOR_NEW_SYMBOL,
    }
