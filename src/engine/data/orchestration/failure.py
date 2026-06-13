"""
Phase 5B — Failure Classification (v0.1)

Classifies failures from Phase 5A acquisition calls and provides recommended actions.
This is foundational for retry policy and alerting hooks in future micro-chunks.
"""

from __future__ import annotations

from typing import Any, Dict


def classify_failure(error: Exception) -> Dict[str, Any]:
    """
    Classifies failure type and returns recommended action + retry policy.
    """
    error_str = str(error).lower()

    if "rate limit" in error_str or "429" in error_str:
        return {
            "failure_type": "rate_limit",
            "recommended_action": "backoff_and_retry",
            "retry_delay_seconds": 300,
            "max_retries": 3,
            "alert": False,
        }
    elif "timeout" in error_str or "connection" in error_str:
        return {
            "failure_type": "transient",
            "recommended_action": "retry",
            "retry_delay_seconds": 60,
            "max_retries": 5,
            "alert": False,
        }
    elif "not found" in error_str or "invalid symbol" in error_str:
        return {
            "failure_type": "permanent",
            "recommended_action": "skip_and_log",
            "retry_delay_seconds": 0,
            "max_retries": 0,
            "alert": False,
        }
    else:
        return {
            "failure_type": "unknown",
            "recommended_action": "log_and_alert",
            "retry_delay_seconds": 0,
            "max_retries": 0,
            "alert": True,
        }
