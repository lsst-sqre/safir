"""Tests for the safir.logging module."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from unittest.mock import ANY

import structlog

from safir.logging import configure_logging

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.logging import LogCaptureFixture


def test_configure_logging_development(caplog: LogCaptureFixture) -> None:
    """Test that development-mode logging is key-value formatted."""
    caplog.set_level(logging.INFO)

    configure_logging(name="myapp", profile="development", log_level="info")

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    assert caplog.record_tuples[0] == (
        "myapp",
        logging.INFO,
        "[info     ] Hello world                    [myapp] answer=42",
    )


def test_configure_logging_dev_timestamp(caplog: LogCaptureFixture) -> None:
    """Test development-mode logging with an added timestamp."""
    caplog.set_level(logging.INFO)

    configure_logging(
        name="myapp",
        profile="development",
        log_level="info",
        add_timestamp=True,
    )

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    assert caplog.record_tuples[0][0] == "myapp"
    assert caplog.record_tuples[0][1] == logging.INFO
    match = re.match(
        (
            r"(\d+-\d+-\d+T\d+:\d+:[\d.]+Z) \[info\s+\] Hello world \s+"
            r" \[myapp\] answer=42"
        ),
        caplog.record_tuples[0][2],
    )
    assert match
    isotimestamp = match.group(1)
    assert isotimestamp.endswith("Z")
    timestamp = datetime.fromisoformat(isotimestamp[:-1])
    timestamp = timestamp.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    assert now - timedelta(seconds=5) < timestamp < now


def test_configure_logging_production(caplog: LogCaptureFixture) -> None:
    """Test that production-mode logging is JSON formatted."""
    caplog.set_level(logging.INFO)

    configure_logging(name="myapp", profile="production", log_level="info")

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    assert caplog.record_tuples[0] == (
        "myapp",
        logging.INFO,
        '{"answer": 42, "event": "Hello world", "logger": "myapp", '
        '"level": "info"}',
    )


def test_configure_logging_prod_timestamp(caplog: LogCaptureFixture) -> None:
    """Test development-mode logging with an added timestamp."""
    caplog.set_level(logging.INFO)

    configure_logging(
        name="myapp",
        profile="production",
        log_level="info",
        add_timestamp=True,
    )

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    assert caplog.record_tuples[0][0] == "myapp"
    assert caplog.record_tuples[0][1] == logging.INFO
    data = json.loads(caplog.record_tuples[0][2])
    assert data == {
        "answer": 42,
        "event": "Hello world",
        "logger": "myapp",
        "level": "info",
        "timestamp": ANY,
    }
    assert data["timestamp"].endswith("Z")
    timestamp = datetime.fromisoformat(data["timestamp"][:-1])
    timestamp = timestamp.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    assert now - timedelta(seconds=5) < timestamp < now


def test_configure_logging_level(caplog: LogCaptureFixture) -> None:
    """Test that the logging level is set."""
    caplog.set_level(logging.DEBUG)

    configure_logging(name="myapp", log_level="info")
    logger = structlog.get_logger("myapp")

    logger.info("INFO message")
    assert len(caplog.record_tuples) == 1

    # debug-level shouldn't get logged
    logger.debug("DEBUG message")
    assert len(caplog.record_tuples) == 1


def test_duplicate_handlers(capsys: CaptureFixture[str]) -> None:
    """Test that configuring logging more than once doesn't duplicate logs."""
    configure_logging(name="myapp", profile="production", log_level="info")
    configure_logging(name="myapp", profile="production", log_level="info")

    logger = structlog.get_logger("myapp")

    logger.info("INFO not duplicate message")
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
