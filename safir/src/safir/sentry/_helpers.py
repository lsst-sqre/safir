"""Sentry helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sentry_sdk.tracing import Span
from sentry_sdk.types import Event, Hint

from ._exceptions import SentryException

__all__ = [
    "before_send_handler",
    "duration",
    "fingerprint_env_handler",
    "sentry_exception_handler",
]


def duration(span: Span) -> timedelta:
    """Return the time spent in a span (to the present if not finished)."""
    if span.timestamp is None:
        timestamp = datetime.now(tz=UTC)
    else:
        timestamp = span.timestamp
    return timestamp - span.start_timestamp


def fingerprint_env_handler(event: Event, _: Hint) -> Event:
    """Add the environment to the event fingerprint.

    Without doing this, Sentry groups events from all environments into the
    same issue, and alerts that notify on new issues won't notify on a prod
    event if an issue has already been created from an event from another env
    :(

    https://github.com/getsentry/sentry/issues/64354
    """
    env = event.get("environment")
    if env is None:
        env = "no environment"
    fingerprint = event.get("fingerprint", [])
    event["fingerprint"] = [
        "{{ default }}",
        *fingerprint,
        env,
    ]
    return event


def sentry_exception_handler(event: Event, hint: Hint) -> Event:
    """Add tags and context from `~safir.sentry.SentryException`."""
    if exc_info := hint.get("exc_info"):
        exc = exc_info[1]
        if isinstance(exc, SentryException):
            exc.enrich(event)
    return event


def before_send_handler(event: Event, hint: Hint) -> Event:
    """Add the env to the fingerprint, and enrich from
    `~safir.sentry.SentryException`.
    """
    event = fingerprint_env_handler(event, hint)
    return sentry_exception_handler(event, hint)
