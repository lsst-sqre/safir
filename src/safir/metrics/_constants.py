"""Constants for metrics functionality."""

from __future__ import annotations

from datetime import timedelta

__all__ = [
    "ADMIN_CLIENT_PREFIX",
    "BROKER_PREFIX",
    "EVENT_MANAGER_DEFAULT_BACKOFF_INTERVAL",
    "EVENT_MANAGER_DEFAULT_KAFKA_TIMEOUT_MS",
]

ADMIN_CLIENT_PREFIX = "safir-metrics-admin-client"
"""Prefix for the client id for the metrics Kafka admin client."""

BROKER_PREFIX = "safir-metrics-faststream-broker"
"""Prefix for the Kafka client id for the metrics FastStream broker."""

EVENT_MANAGER_DEFAULT_BACKOFF_INTERVAL = timedelta(seconds=300)
"""Amount of time to wait before taking event manager out of error mode."""

EVENT_MANAGER_DEFAULT_KAFKA_TIMEOUT_MS = 1000
"""How long to wait for Kafka before raising an error for a blocking call."""
