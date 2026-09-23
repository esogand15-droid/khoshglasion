"""Retry only transient provider failures. A 404 is a wrong route, not a blip."""
from __future__ import annotations

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def should_retry_status(status: int) -> bool:
    return int(status) in RETRYABLE_STATUS


def retry_wait_seconds(attempt: int, retry_after: float | None = None) -> float:
    if retry_after is not None:
        try:
            hinted = float(retry_after)
        except (TypeError, ValueError):
            hinted = 0
        if hinted > 0:
            return min(hinted, 8)
    return min(8.0, 0.4 * (2 ** max(0, attempt)))
