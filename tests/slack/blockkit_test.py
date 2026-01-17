"""Test Slack client."""

from __future__ import annotations

import pickle
from textwrap import dedent

import pytest
import respx
import sentry_sdk
import structlog
from httpx import AsyncClient, HTTPError, Response
from pydantic import ValidationError

from safir.slack.blockkit import (
    SlackBaseField,
    SlackCodeBlock,
    SlackCodeField,
    SlackException,
    SlackMessage,
    SlackTextBlock,
    SlackTextField,
    SlackWebException,
)
from safir.slack.webhook import SlackWebhookClient
from safir.testing.data import Data
from safir.testing.sentry import Captured
from safir.testing.slack import MockSlackWebhook


def test_message(data: Data) -> None:
    # Unfortunately, because blocks, attachments, and fields are lists of base
    # classes, SlackMessage objects cannot be deserialized from JSON. We
    # therefore have to inline the object definitions rather than using
    # data.read_pydantic until we're willing to make a breaking change to the
    # data structures.
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
    data.assert_json_matches(message.to_slack(), "slack/message")

    message = SlackMessage(message="Single line message", verbatim=False)
    data.assert_json_matches(message.to_slack(), "slack/single-line")

    message = SlackMessage(
        message="Message with <special> & one `field`",
        fields=[SlackTextField(heading="Something", text="Blah")],
    )
    data.assert_json_matches(message.to_slack(), "slack/special")

    message = SlackMessage(
        message="Message with one block",
        blocks=[SlackTextBlock(heading="Something", text="Blah")],
    )
    data.assert_json_matches(message.to_slack(), "slack/one-block")


def test_validation() -> None:
    """Test errors caught by validation."""
    field: SlackBaseField = SlackTextField(heading="Something", text="foo")
    fields = [field] * 11
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


@pytest.mark.asyncio
async def test_exception(data: Data, mock_slack: MockSlackWebhook) -> None:
    logger = structlog.get_logger(__file__)
    slack = SlackWebhookClient(mock_slack.url, "App", logger)

    class SomeError(SlackException):
        pass

    try:
        raise SomeError("Some error", "someuser")
    except SlackException as e:
        await slack.post_exception(e)

    data.assert_json_matches(mock_slack.messages, "slack/exception")


class SlackSubclassException(SlackException):
    """Subclsas for testing pickling."""

    def __init__(self) -> None:
        super().__init__("Some error", "username")


def test_exception_pickling() -> None:
    """Test that a `SlackException` can be pickled and unpickled.

    Errors that may be raised by backend workers in an arq queue must support
    pickling so that they can be passed correctly to other workers or the
    frontend.
    """
    exc = SlackException("some message", "username")
    pickled_exc = pickle.loads(pickle.dumps(exc))
    assert exc.to_slack() == pickled_exc.to_slack()

    # Try the same with a derived class with a different number of constructor
    # arguments.
    subexc = SlackSubclassException()
    pickled_subexc = pickle.loads(pickle.dumps(subexc))
    assert subexc.to_slack() == pickled_subexc.to_slack()


@pytest.mark.asyncio
async def test_web_exception(
    data: Data, respx_mock: respx.Router, mock_slack: MockSlackWebhook
) -> None:
    logger = structlog.get_logger(__file__)
    slack = SlackWebhookClient(mock_slack.url, "App", logger)

    class SomeError(SlackWebException):
        pass

    respx_mock.get("https://example.org/").mock(return_value=Response(404))
    exception = None
    try:
        async with AsyncClient() as client:
            r = await client.get("https://example.org/")
            r.raise_for_status()
    except HTTPError as e:
        exception = SomeError.from_exception(e)
        assert str(exception) == "Status 404 from GET https://example.org/"
        await slack.post_exception(exception)

    data.assert_json_matches(mock_slack.messages, "slack/web-exception")


@pytest.mark.asyncio
async def test_web_exception_sentry(
    respx_mock: respx.Router,
    sentry_combo_items: Captured,
) -> None:
    class SomeError(SlackWebException):
        pass

    respx_mock.get("https://example.org/").mock(
        return_value=Response(404, text="some response body")
    )
    exception = None
    try:
        async with AsyncClient() as client:
            r = await client.get("https://example.org/")
            r.raise_for_status()
    except HTTPError as e:
        exception = SomeError.from_exception(e)
        stringified = dedent("""\
            Status 404 from GET https://example.org/
            Body:
            some response body
        """)
        assert str(exception) == stringified
        sentry_sdk.capture_exception(exception)

    (error,) = sentry_combo_items.errors
    assert error["tags"]["httpx_request_method"] == "GET"
    assert error["tags"]["httpx_request_url"] == "https://example.org/"

    (attachment,) = sentry_combo_items.attachments
    assert attachment.filename == "httpx_response_body"
    assert attachment.bytes.decode() == "some response body"
