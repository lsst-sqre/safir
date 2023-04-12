"""Test Slack client."""

from __future__ import annotations

from unittest.mock import ANY

import pytest
import structlog
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from safir.datetime import current_datetime, format_datetime_for_logging
from safir.slack.blockkit import SlackException, SlackMessage
from safir.slack.webhook import (
    SlackIgnoredException,
    SlackRouteErrorHandler,
    SlackWebhookClient,
)
from safir.testing.slack import MockSlackWebhook


@pytest.mark.asyncio
async def test_post(mock_slack: MockSlackWebhook) -> None:
    message = SlackMessage(message="Some random message")
    logger = structlog.get_logger(__file__)
    client = SlackWebhookClient(mock_slack.url, "App", logger)
    await client.post(message)
    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Some random message",
                        "verbatim": True,
                    },
                }
            ]
        }
    ]


@pytest.mark.asyncio
async def test_post_exception(mock_slack: MockSlackWebhook) -> None:
    logger = structlog.get_logger(__file__)
    client = SlackWebhookClient(mock_slack.url, "App", logger)

    exc = SlackException("Some exception message")
    await client.post_exception(exc)
    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error in App: Some exception message",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": "*Exception type*\nSlackException",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": ANY,
                            "verbatim": True,
                        },
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]
    mock_slack.messages = []

    class TestException(SlackException):
        pass

    now = current_datetime()
    now_formatted = format_datetime_for_logging(now)
    exc = TestException("Blah blah blah", "username", failed_at=now)
    await client.post_exception(exc)
    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error in App: Blah blah blah",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": "*Exception type*\nTestException",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Failed at*\n{now_formatted}",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*User*\nusername",
                            "verbatim": True,
                        },
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]


@pytest.mark.asyncio
async def test_route_handler(mock_slack: MockSlackWebhook) -> None:
    """Test Slack alerts for uncaught exceptions."""
    router = APIRouter(route_class=SlackRouteErrorHandler)

    class SomeAppError(SlackIgnoredException):
        pass

    class OtherAppError(SlackException):
        pass

    @router.get("/exception")
    async def get_exception() -> None:
        raise ValueError("Test exception")

    @router.get("/ignored")
    async def get_ignored() -> None:
        raise SomeAppError("Test exception")

    @router.get("/known")
    async def get_known() -> None:
        raise OtherAppError("Slack exception")

    app = FastAPI()
    app.include_router(router)

    # We need a custom HTTPX configuration to disable raising server
    # exceptions so that we can inspect the resulting error handling.
    transport = ASGITransport(
        app=app,  # type: ignore[arg-type]
        raise_app_exceptions=False,
    )

    # Run the test.
    base_url = "https://example.com"
    async with AsyncClient(transport=transport, base_url=base_url) as client:
        r = await client.get("/exception")
        assert r.status_code == 500

        # Slack alerting has not been configured yet, so nothing should be
        # posted to Slack.
        assert mock_slack.messages == []

        # Configure Slack alerting and raise an ignored exception. There
        # should still be nothing posted to Slack.
        logger = structlog.get_logger(__file__)
        SlackRouteErrorHandler.initialize(mock_slack.url, "App", logger)
        r = await client.get("/ignored")
        assert r.status_code == 500
        assert mock_slack.messages == []

        # But now raising another exception should result in a Slack message.
        r = await client.get("/exception")
        assert r.status_code == 500

        # And raising an exception that inherits from SlackException should
        # result in nicer formatting.
        r = await client.get("/known")
        assert r.status_code == 500

    # Check that the Slack alert was what we expected.
    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Uncaught exception in App",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": "*Exception type*\nValueError",
                            "verbatim": True,
                        },
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "*Exception*\n```\nValueError: Test exception\n```"
                        ),
                        "verbatim": True,
                    },
                },
                {"type": "divider"},
            ],
        },
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ("Uncaught exception in App: Slack exception"),
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": "*Exception type*\nOtherAppError",
                            "verbatim": True,
                        },
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                    ],
                },
                {"type": "divider"},
            ],
        },
    ]
    assert mock_slack.messages[0]["blocks"][1]["fields"][1]["text"].startswith(
        "*Failed at*\n"
    )
