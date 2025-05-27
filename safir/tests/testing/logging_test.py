"""Tests for the safir.testing.logging module."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

import pytest
import structlog

from safir.datetime import isodatetime
from safir.logging import LogLevel, Profile, configure_logging
from safir.testing.logging import parse_log_tuples


def test_parse_log_tuples(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging(
        name="myapp",
        profile=Profile.production,
        log_level=LogLevel.INFO,
        add_timestamp=True,
    )

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    assert parse_log_tuples("myapp", caplog.record_tuples) == [
        {
            "answer": 42,
            "event": "Hello world",
            "severity": "info",
        }
    ]
    assert parse_log_tuples("otherapp", caplog.record_tuples) == []

    test_tuples = [
        (
            "myapp",
            logging.INFO,
            json.dumps(
                {
                    "event": "Some message",
                    "httpRequest": {
                        "remoteIp": "127.0.0.1",
                        "requestMethod": "GET",
                        "requestUrl": "https://example.com/",
                        "userAgent": "some-user-agent/1.0",
                    },
                    "logger": "myapp",
                    "request_id": str(uuid.uuid4()),
                    "severity": "info",
                    "timestamp": isodatetime(datetime.now(tz=UTC)),
                }
            ),
        ),
        (
            "myapp",
            logging.DEBUG,
            json.dumps(
                {
                    "event": "Debug message",
                    "logger": "myapp",
                    "severity": "debug",
                }
            ),
        ),
        (
            "otherapp",
            logging.WARNING,
            json.dumps(
                {
                    "event": "Warning message",
                    "logger": "otherapp",
                    "severity": "warning",
                }
            ),
        ),
    ]
    expected = [
        {
            "event": "Some message",
            "httpRequest": {
                "remoteIp": "127.0.0.1",
                "requestMethod": "GET",
                "requestUrl": "https://example.com/",
            },
            "severity": "info",
        },
        {
            "event": "Debug message",
            "severity": "debug",
        },
    ]
    assert parse_log_tuples("myapp", test_tuples) == expected
    filtered = parse_log_tuples("myapp", test_tuples, ignore_debug=True)
    assert filtered == expected[0:1]

    with pytest.raises(AssertionError, match="logger "):
        parse_log_tuples(
            "myapp", [("myapp", logging.INFO, json.dumps({"logger": "foo"}))]
        )
    with pytest.raises(AssertionError, match="severity "):
        parse_log_tuples(
            "myapp",
            [
                (
                    "myapp",
                    logging.INFO,
                    json.dumps({"logger": "myapp", "severity": "warning"}),
                )
            ],
        )
    with pytest.raises(AssertionError, match="endswith"):
        parse_log_tuples(
            "myapp",
            [
                (
                    "myapp",
                    logging.INFO,
                    json.dumps(
                        {
                            "event": "Message",
                            "logger": "myapp",
                            "severity": "info",
                            "timestamp": "2025-05-27T12:23:45",
                        }
                    ),
                )
            ],
        )
    with pytest.raises(AssertionError, match="within 1 hour"):
        parse_log_tuples(
            "myapp",
            [
                (
                    "myapp",
                    logging.INFO,
                    json.dumps(
                        {
                            "event": "Message",
                            "logger": "myapp",
                            "severity": "info",
                            "timestamp": "2025-05-27T10:23:45Z",
                        }
                    ),
                )
            ],
        )
