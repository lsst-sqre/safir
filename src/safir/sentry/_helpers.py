"""Sentry helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sentry_sdk
from sentry_sdk.attachments import Attachment
from sentry_sdk.tracing import Span
from sentry_sdk.types import Event, Hint

from safir.slack.webhook import SlackIgnoredException, SlackWebhookClient

from ..slack.blockkit import SlackException

__all__ = [
    "before_send_handler",
    "duration",
    "fingerprint_env_handler",
    "report_exception",
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
    """Add tags and context from `~safir.slack.blockkit.SlackException`.

    The Sentry event data model is:
    https://develop.sentry.dev/sdk/data-model/event-payloads/
    """
    if exc_info := hint.get("exc_info"):
        exc = exc_info[1]
        if isinstance(exc, SlackException):
            info = exc.to_sentry()
            event["tags"] = event.setdefault("tags", {})
            event["tags"].update(info.tags)
            event["contexts"] = event.setdefault("contexts", {})
            event["contexts"].update(info.contexts)

            if info.username:
                event["user"] = event.setdefault("user", {})
                event["user"]["username"] = info.username

            for key, content in info.attachments.items():
                attachments = hint.setdefault("attachments", [])
                attachments.append(
                    Attachment(filename=key, bytes=content.encode())
                )

    return event


def before_send_handler(event: Event, hint: Hint) -> Event:
    """Add the env to the fingerprint, and enrich from
    `~safir.slack.blockkit.SlackException`.
    """
    event = fingerprint_env_handler(event, hint)
    return sentry_exception_handler(event, hint)


async def report_exception(
    exc: Exception, slack_client: SlackWebhookClient | None
) -> None:
    """Notify Sentry and Slack about an exception.

    Use this when you want to be notified about an exception, but stop
    propagating it. If you want to keep propagating the exception and still
    support both Slack and Sentry, catch the exception, use
    `~safir.slack.webhook.SlackWebhookClient.post_exception`, re-raise the
    exception, and let the Sentry-configured uncaught exception handler notify
    Sentry if the exception makes it that far.

    If Sentry has not been initialized, then no events will be sent to Sentry.
    If ``slack_client`` is `None`, then no notifications will be sent to
    Slack.

    If the exception is an instance of
    `~safir.slack.webhook.SlackIgnoredException`, no notifications will be
    sent to either Sentry or Slack. If the exception is an instance of
    `~safir.slack.blockkit.SlackException`, the Slack message will be generated
    from its ``to_slack`` method.

    Parameters
    ----------
    exc
        The Exception to send to the notification service.

    slack_client
        A client to use to send a Slack notification about the exception. If \
        this is `None`, then no Slack notification will be sent.
    """
    if isinstance(exc, SlackIgnoredException):
        return

    sentry_sdk.capture_exception(exc)
    if slack_client:
        await slack_client.post_exception(exc)
