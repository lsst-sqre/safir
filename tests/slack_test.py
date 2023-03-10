"""Test Slack client."""

from __future__ import annotations

from unittest.mock import ANY

import pytest
import structlog
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from safir.datetime import current_datetime, format_datetime_for_logging
from safir.slack import (
    SlackAttachment,
    SlackClient,
    SlackException,
    SlackField,
    SlackMessage,
    SlackRouteErrorHandler,
)
from safir.testing.slack import MockSlack


def test_message() -> None:
    message = SlackMessage(
        message="This is some *Slack message*  \n  ",
        fields=[
            SlackField(heading="Some text", text="Value of the field   "),
            SlackField(heading="Some code", code="Here is\nthe code\n"),
        ],
        attachments=[
            SlackAttachment(heading="Backtrace", code="Some\nlong\nbacktrace"),
            SlackAttachment(heading="Essay", text="Blah blah blah"),
        ],
    )
    assert message.to_slack() == {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "This is some *Slack message*",
                    "verbatim": False,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": "*Some text*\nValue of the field",
                        "verbatim": True,
                    },
                    {
                        "type": "mrkdwn",
                        "text": ("*Some code*\n```\nHere is\nthe code\n```"),
                        "verbatim": True,
                    },
                ],
            },
        ],
        "attachments": [
            {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "*Backtrace*\n```\nSome\nlong\nbacktrace\n```"
                            ),
                            "verbatim": True,
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Essay*\nBlah blah blah",
                            "verbatim": True,
                        },
                    },
                ]
            }
        ],
    }

    message = SlackMessage(message="Single line message", verbatim=True)
    assert message.to_slack() == {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Single line message",
                    "verbatim": True,
                },
            }
        ]
    }

    message = SlackMessage(
        message="Message with one `field`",
        fields=[SlackField(heading="Something", text="Blah")],
    )
    assert message.to_slack() == {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Message with one `field`",
                    "verbatim": False,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": "*Something*\nBlah",
                        "verbatim": True,
                    },
                ],
            },
            {"type": "divider"},
        ]
    }


def test_validation() -> None:
    """Test various errors caught by validation (but not truncation)."""
    with pytest.raises(ValidationError):
        SlackField(heading="Something")
    with pytest.raises(ValidationError):
        SlackField(heading="Something", text="foo", code="bar")

    # At most ten fields are allowed.
    fields = [SlackField(heading="Something", text="foo")] * 11
    message = SlackMessage(message="Ten fields", fields=fields[:10])
    assert len(message.fields) == 10
    with pytest.raises(ValidationError):
        SlackMessage(message="Eleven fields", fields=fields)


def test_field_truncation() -> None:
    """Test truncating fields at Slack limits."""
    field = SlackField(heading="Something", text="a" * 2000)
    length = 2000 - len("*Something*\n\n... truncated ...")
    assert field.to_slack()["text"] == (
        "*Something*\n" + "a" * length + "\n... truncated ..."
    )

    field = SlackField(heading="Something", text="abcdefg\n" * 250)
    length = int((2001 - len("*Something*\n\n... truncated ...")) / 8)
    assert field.to_slack()["text"] == (
        "*Something*\n" + "abcdefg\n" * length + "... truncated ..."
    )

    field = SlackField(heading="Else", code="a" * 2000)
    length = 2000 - len("*Else*\n```\n... truncated ...\n\n```")
    assert field.to_slack()["text"] == (
        "*Else*\n```\n... truncated ...\n" + "a" * length + "\n```"
    )

    field = SlackField(heading="Else", code="abcdefg\n" * 250)
    length = int((2001 - len("*Else*\n```\n... truncated ...\n\n```")) / 8)
    assert field.to_slack()["text"] == (
        "*Else*\n```\n... truncated ...\n"
        + ("abcdefg\n" * length).strip()
        + "\n```"
    )


def test_attachment_truncation() -> None:
    """Test truncating attachments at Slack limits."""
    attachment = SlackAttachment(heading="Something", text="a" * 3000)
    length = 3000 - len("*Something*\n\n... truncated ...")
    assert attachment.to_slack()["text"] == (
        "*Something*\n" + "a" * length + "\n... truncated ..."
    )

    attachment = SlackAttachment(heading="Something", text="abcde\n" * 500)
    length = int((3001 - len("*Something*\n\n... truncated ...")) / 6)
    assert attachment.to_slack()["text"] == (
        "*Something*\n" + "abcde\n" * length + "... truncated ..."
    )

    attachment = SlackAttachment(heading="Else", code="a" * 3000)
    length = 3000 - len("*Else*\n```\n... truncated ...\n\n```")
    assert attachment.to_slack()["text"] == (
        "*Else*\n```\n... truncated ...\n" + "a" * length + "\n```"
    )

    attachment = SlackAttachment(heading="Else", code="abcde\n" * 500)
    length = int((3001 - len("*Else*\n```\n... truncated ...\n\n```")) / 6)
    assert attachment.to_slack()["text"] == (
        "*Else*\n```\n... truncated ...\n"
        + ("abcde\n" * length).strip()
        + "\n```"
    )


def test_message_truncation() -> None:
    """Text truncating the main part of a Slack message."""
    message = SlackMessage(message="a" * 3000)
    assert message.to_slack()["blocks"][0]["text"]["text"] == "a" * 3000
    message = SlackMessage(message="a" * 3001)
    length = 3000 - len("\n... truncated ...")
    assert message.to_slack()["blocks"][0]["text"]["text"] == (
        "a" * length + "\n... truncated ..."
    )


@pytest.mark.asyncio
async def test_post(mock_slack: MockSlack) -> None:
    message = SlackMessage(message="Some random message")
    logger = structlog.get_logger(__file__)
    client = SlackClient(mock_slack.url, "App", logger)
    await client.post(message)
    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Some random message",
                        "verbatim": False,
                    },
                }
            ]
        }
    ]


@pytest.mark.asyncio
async def test_post_exception(mock_slack: MockSlack) -> None:
    logger = structlog.get_logger(__file__)
    client = SlackClient(mock_slack.url, "App", logger)

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
async def test_route_handler(mock_slack: MockSlack) -> None:
    """Test Slack alerts for uncaught exceptions."""
    router = APIRouter(route_class=SlackRouteErrorHandler)

    @router.get("/exception")
    async def get_exception() -> None:
        raise ValueError("Test exception")

    app = FastAPI()
    app.include_router(router)

    # We need a custom httpx configuration to disable raising server
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

        # Configure Slack alerting and repeat the test.
        logger = structlog.get_logger(__file__)
        SlackRouteErrorHandler.initialize(mock_slack.url, "App", logger)
        r = await client.get("/exception")
        assert r.status_code == 500

    # Check that the Slack alert was what we expected.
    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Uncaught ValueError exception in App",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True}
                    ],
                },
            ],
            "attachments": [
                {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "*Exception*\n```\n"
                                    "ValueError: Test exception\n```"
                                ),
                                "verbatim": True,
                            },
                        }
                    ]
                }
            ],
        }
    ]
    assert mock_slack.messages[0]["blocks"][1]["fields"][0]["text"].startswith(
        "*Failed at*\n"
    )
