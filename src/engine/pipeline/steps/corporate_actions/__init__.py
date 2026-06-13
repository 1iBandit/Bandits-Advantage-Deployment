"""
Corporate Actions Module (v1)

Stand-alone module for fetching and normalizing dividends and splits from MASSIVE
(same client and MASSIVE_API_KEY as the news module; user correction: not Polygon).

Provides clean, defensive access to corporate action data for diagnostics,
quality screens, income modeling, and future integration into Scorecard / OutlierEvent.

See corporate_actions.py for full implementation, output shapes, and usage.

Exports:
- get_dividends
- get_splits
- get_corporate_actions
- batch_get_corporate_actions
"""

from .corporate_actions import (
    get_dividends,
    get_splits,
    get_corporate_actions,
    batch_get_corporate_actions,
    build_corporate_action_context,
)

__all__ = [
    "get_dividends",
    "get_splits",
    "get_corporate_actions",
    "batch_get_corporate_actions",
    "build_corporate_action_context",
]
