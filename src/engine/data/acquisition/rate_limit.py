"""
Phase 5C — Rate Limit Handling

Detection of rate limits (429) from Polygon and simple backoff logic.
Integrated with 5B's failure classification.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from ..orchestration.failure import classify_failure  # reuse 5B classifier


def handle_rate_limit(
    error: Exception,
    retry_count: int = 0,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Detect rate limit, apply backoff, and return decision.
    """
    classification = classify_failure(error)

    if classification.get("failure_type") == "rate_limit":
        delay = classification.get("retry_delay_seconds", 300) * (2 ** retry_count)  # exponential
        if retry_count < max_retries:
            time.sleep(delay)
            return {
                "action": "retry",
                "delay_seconds": delay,
                "retry_count": retry_count + 1,
                "classification": classification,
            }
        else:
            return {
                "action": "fallback_to_synthetic",
                "delay_seconds": 0,
                "retry_count": retry_count,
                "classification": classification,
            }

    # For other errors, let caller decide
    return {
        "action": "error",
        "classification": classification,
    }
