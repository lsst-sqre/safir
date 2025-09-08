"""Constants for the UWS work queue."""

from __future__ import annotations

from datetime import timedelta

__all__ = [
    "JOB_RESULT_TIMEOUT",
    "JOB_STOP_TIMEOUT",
    "UWS_DATABASE_TIMEOUT",
    "WOBBLY_REQUEST_TIMEOUT",
]

JOB_RESULT_TIMEOUT = timedelta(seconds=5)
"""How long to poll arq for job results before giving up."""

JOB_STOP_TIMEOUT = timedelta(seconds=30)
"""How long to wait for a job to stop before giving up."""

UWS_DATABASE_TIMEOUT = timedelta(seconds=30)
"""Timeout on workers that update the UWS database.

This should match the default Kubernetes grace period for a pod to shut down.
"""

WOBBLY_REQUEST_TIMEOUT = 20
"""Timeout in seconds for Wobbly HTTP requests."""
