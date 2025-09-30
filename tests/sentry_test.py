"""Tests for Sentry helpers."""

from typing import override
from unittest.mock import ANY

import pytest
import sentry_sdk
import structlog

from safir.sentry._helpers import report_exception
from safir.slack.blockkit import SentryEventInfo, SlackException
from safir.slack.webhook import SlackIgnoredException, SlackWebhookClient
from safir.testing.sentry import Captured
from safir.testing.slack._mocks import MockSlackWebhook


class SomeError(SlackException):
    """An exception type to test before_send handling."""

    def __init__(self, woo: str, bar: str, user: str | None = None) -> None:
        super().__init__(message="Boom!", user=user)
        self.woo = woo
        self.bar = bar
        self.user = user

    @override
    def to_sentry(self) -> SentryEventInfo:
        info = super().to_sentry()
        info.tags["woo"] = self.woo
        info.contexts["foo"] = {"bar": self.bar}
        return info


def test_env_fingerprint_before_send(
    sentry_fingerprint_items: Captured,
) -> None:
    sentry_sdk.capture_exception(Exception("some error"))
    (error,) = sentry_fingerprint_items.errors
    assert error["fingerprint"] == ["{{ default }}", "some_env"]


def test_sentry_exception_before_send(
    sentry_exception_items: Captured,
) -> None:
    exc = SomeError(woo="hoo", bar="baz", user="someuser")

    sentry_sdk.capture_exception(exc)

    (error,) = sentry_exception_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["tags"] == {"woo": "hoo"}
    assert error["user"]["username"] == "someuser"


def test_combined_before_send(sentry_combo_items: Captured) -> None:
    exc = SomeError(woo="hoo", bar="baz", user="someuser")

    sentry_sdk.capture_exception(exc)

    (error,) = sentry_combo_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["fingerprint"] == ["{{ default }}", "some_env"]
    assert error["tags"] == {"woo": "hoo"}
    assert error["user"]["username"] == "someuser"


@pytest.mark.asyncio
async def test_report_exception_both(
    mock_slack: MockSlackWebhook, sentry_combo_items: Captured
) -> None:
    logger = structlog.get_logger(__file__)
    client = SlackWebhookClient(mock_slack.url, "App", logger)
    exc = SomeError(woo="hoo", bar="baz", user="someuser")

    await report_exception(exc, slack_client=client)

    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error in App: Boom!",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": "*Exception type*\nSomeError",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": ANY,
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*User*\nsomeuser",
                            "verbatim": True,
                        },
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]

    (error,) = sentry_combo_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["fingerprint"] == ["{{ default }}", "some_env"]
    assert error["tags"] == {"woo": "hoo"}
    assert error["user"]["username"] == "someuser"


@pytest.mark.asyncio
async def test_report_exception_sentry_only(
    mock_slack: MockSlackWebhook, sentry_combo_items: Captured
) -> None:
    exc = SomeError(woo="hoo", bar="baz", user="someuser")

    await report_exception(exc, slack_client=None)

    assert mock_slack.messages == []

    (error,) = sentry_combo_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["fingerprint"] == ["{{ default }}", "some_env"]
    assert error["tags"] == {"woo": "hoo"}
    assert error["user"]["username"] == "someuser"


@pytest.mark.asyncio
async def test_report_exception_ignores(
    mock_slack: MockSlackWebhook, sentry_combo_items: Captured
) -> None:
    class IgnoredError(SlackIgnoredException):
        pass

    logger = structlog.get_logger(__file__)
    client = SlackWebhookClient(mock_slack.url, "App", logger)
    exc = IgnoredError()

    await report_exception(exc, slack_client=client)

    assert mock_slack.messages == []
    assert sentry_combo_items.errors == []
