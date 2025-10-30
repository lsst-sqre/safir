"""Test Kafka exception functionality."""

from collections.abc import AsyncGenerator
from unittest.mock import ANY

import pytest
import pytest_asyncio
from faststream.kafka import KafkaBroker
from faststream.kafka.testing import TestKafkaBroker
from structlog.stdlib import get_logger

from safir.kafka import FastStreamErrorHandler
from safir.testing.sentry import Captured
from safir.testing.slack import MockSlackWebhook


@pytest_asyncio.fixture
async def error_handling_faststream_broker(
    faststream_error_handler: FastStreamErrorHandler,
) -> AsyncGenerator[KafkaBroker]:
    """Yield A FastStream Kafka broker with error reporting middleware."""
    broker = KafkaBroker(
        middlewares=[faststream_error_handler.make_middleware()]
    )

    @broker.subscriber("test-with-errors")
    async def handler_with_error(foo: str) -> None:
        _ = 1 / 0

    @broker.subscriber("test-without-errors")
    async def handler_without_error(foo: str) -> None:
        return

    async with TestKafkaBroker(broker) as br:
        yield br


@pytest.mark.asyncio
async def test_faststream_error_handler_doesnt_error(
    error_handling_faststream_broker: KafkaBroker,
) -> None:
    broker = error_handling_faststream_broker
    await broker.publish("whatever", topic="test-without-errors")


@pytest.mark.asyncio
async def test_faststream_error_handler_reraises(
    error_handling_faststream_broker: KafkaBroker,
) -> None:
    broker = error_handling_faststream_broker
    with pytest.raises(ZeroDivisionError):
        await broker.publish("whatever", topic="test-with-errors")


@pytest.mark.asyncio
async def test_faststream_error_handler_reports_slack(
    error_handling_faststream_broker: KafkaBroker,
    faststream_error_handler: FastStreamErrorHandler,
    mock_slack: MockSlackWebhook,
) -> None:
    faststream_error_handler.initialize_slack(
        hook_url=mock_slack.url,
        application="my-app",
        logger=get_logger(),
    )
    broker = error_handling_faststream_broker
    with pytest.raises(ZeroDivisionError):
        await broker.publish("whatever", topic="test-with-errors")

    expected = [
        {
            "blocks": [
                {
                    "text": {
                        "text": "Error in my-app",
                        "type": "mrkdwn",
                        "verbatim": True,
                    },
                    "type": "section",
                },
                {
                    "fields": [
                        {
                            "text": "*Exception type*\nZeroDivisionError",
                            "type": "mrkdwn",
                            "verbatim": True,
                        },
                        {
                            "text": ANY,
                            "type": "mrkdwn",
                            "verbatim": True,
                        },
                    ],
                    "type": "section",
                },
                {
                    "text": {
                        "text": "*Exception*\n"
                        "```\n"
                        "ZeroDivisionError: division by zero\n"
                        "```",
                        "type": "mrkdwn",
                        "verbatim": True,
                    },
                    "type": "section",
                },
                {
                    "type": "divider",
                },
            ],
        },
    ]

    assert mock_slack.messages == expected


@pytest.mark.asyncio
async def test_faststream_error_handler_reports_sentry(
    error_handling_faststream_broker: KafkaBroker,
    sentry_combo_items: Captured,
) -> None:
    broker = error_handling_faststream_broker
    with pytest.raises(ZeroDivisionError):
        await broker.publish("whatever", topic="test-with-errors")
    (error,) = sentry_combo_items.errors
    (exception,) = error["exception"]["values"]
    assert exception["type"] == "ZeroDivisionError"
