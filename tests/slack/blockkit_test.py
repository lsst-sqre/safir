"""Test Slack client."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from safir.slack.blockkit import (
    SlackCodeBlock,
    SlackCodeField,
    SlackMessage,
    SlackTextBlock,
    SlackTextField,
)


def test_message() -> None:
    message = SlackMessage(
        message="This is some *Slack message*  \n  ",
        fields=[
            SlackTextField(heading="Some text", text="Value of the field   "),
            SlackCodeField(heading="Some code", code="Here is\nthe code\n"),
        ],
        blocks=[SlackTextBlock(heading="Log", text="Some\nlong\nlog")],
        attachments=[
            SlackCodeBlock(heading="Backtrace", code="Some\nbacktrace"),
            SlackTextBlock(heading="Essay", text="Blah blah blah"),
        ],
    )
    assert message.to_slack() == {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "This is some *Slack message*",
                    "verbatim": True,
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
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Log*\nSome\nlong\nlog",
                    "verbatim": True,
                },
            },
        ],
        "attachments": [
            {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ("*Backtrace*\n```\nSome\nbacktrace\n```"),
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

    message = SlackMessage(message="Single line message", verbatim=False)
    assert message.to_slack() == {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Single line message",
                    "verbatim": False,
                },
            }
        ]
    }

    message = SlackMessage(
        message="Message with <special> & one `field`",
        fields=[SlackTextField(heading="Something", text="Blah")],
    )
    assert message.to_slack() == {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Message with &lt;special&gt; &amp; one `field`",
                    "verbatim": True,
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

    message = SlackMessage(
        message="Message with one block",
        blocks=[SlackTextBlock(heading="Something", text="Blah")],
    )
    assert message.to_slack() == {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Message with one block",
                    "verbatim": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Something*\nBlah",
                    "verbatim": True,
                },
            },
            {"type": "divider"},
        ]
    }


def test_validation() -> None:
    """Test errors caught by validation."""
    fields = [SlackTextField(heading="Something", text="foo")] * 11
    message = SlackMessage(message="Ten fields", fields=fields[:10])
    assert len(message.fields) == 10
    with pytest.raises(ValidationError):
        SlackMessage(message="Eleven fields", fields=fields)


def test_block_truncation() -> None:
    """Test truncating attachments at Slack limits."""
    block = SlackTextBlock(heading="Something", text="a" * 3000)
    length = 3000 - len("*Something*\n\n... truncated ...")
    assert block.to_slack()["text"] == (
        "*Something*\n" + "a" * length + "\n... truncated ..."
    )

    block = SlackTextBlock(heading="Something", text="abcde\n" * 500)
    length = int((3001 - len("*Something*\n\n... truncated ...")) / 6)
    assert block.to_slack()["text"] == (
        "*Something*\n" + "abcde\n" * length + "... truncated ..."
    )

    cblock = SlackCodeBlock(heading="Else", code="a" * 3000)
    length = 3000 - len("*Else*\n```\n... truncated ...\n\n```")
    assert cblock.to_slack()["text"] == (
        "*Else*\n```\n... truncated ...\n" + "a" * length + "\n```"
    )

    cblock = SlackCodeBlock(heading="Else", code="abcde\n" * 500)
    length = int((3001 - len("*Else*\n```\n... truncated ...\n\n```")) / 6)
    assert cblock.to_slack()["text"] == (
        "*Else*\n```\n... truncated ...\n"
        + ("abcde\n" * length).strip()
        + "\n```"
    )


def test_field_truncation() -> None:
    """Test truncating fields at Slack limits."""
    field = SlackTextField(heading="Something", text="a" * 2000)
    length = 2000 - len("*Something*\n\n... truncated ...")
    assert field.to_slack()["text"] == (
        "*Something*\n" + "a" * length + "\n... truncated ..."
    )

    field = SlackTextField(heading="Something", text="abcdefg\n" * 250)
    length = int((2001 - len("*Something*\n\n... truncated ...")) / 8)
    assert field.to_slack()["text"] == (
        "*Something*\n" + "abcdefg\n" * length + "... truncated ..."
    )

    cfield = SlackCodeField(heading="Else", code="a" * 2000)
    length = 2000 - len("*Else*\n```\n... truncated ...\n\n```")
    assert cfield.to_slack()["text"] == (
        "*Else*\n```\n... truncated ...\n" + "a" * length + "\n```"
    )

    cfield = SlackCodeField(heading="Else", code="abcdefg\n" * 250)
    length = int((2001 - len("*Else*\n```\n... truncated ...\n\n```")) / 8)
    assert cfield.to_slack()["text"] == (
        "*Else*\n```\n... truncated ...\n"
        + ("abcdefg\n" * length).strip()
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
