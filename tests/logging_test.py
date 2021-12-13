"""Tests for the safir.logging module."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from unittest.mock import ANY

import structlog

from safir import logging as safir_logging
from safir.logging import configure_logging

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.logging import LogCaptureFixture


def _strip_color(string: str) -> str:
    """Strip ANSI color escape sequences.

    See https://stackoverflow.com/questions/14693701/
    """
    return re.sub(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]", "", string)


def test_configure_logging_development(caplog: LogCaptureFixture) -> None:
    """Test that development-mode logging is key-value formatted."""
    caplog.set_level(logging.INFO)

    configure_logging(name="myapp", profile="development", log_level="info")
    assert safir_logging.logger_name == "myapp"

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    app, level, line = caplog.record_tuples[0]
    assert app == "myapp"
    assert level == logging.INFO
    expected = "[info     ] Hello world                    [myapp] answer=42"
    assert _strip_color(line) == expected


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
        _strip_color(caplog.record_tuples[0][2]),
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
        '"severity": "info"}',
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
        "severity": "info",
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


def test_dev_exception_logging(caplog: LogCaptureFixture) -> None:
    """Test that exceptions are properly logged in the development logger."""
    configure_logging(name="myapp", profile="development", log_level="info")
    logger = structlog.get_logger("myapp")

    try:
        raise ValueError("this is some exception")
    except Exception:
        logger.exception("exception happened", foo="bar")

    assert caplog.record_tuples[0][0] == "myapp"
    assert caplog.record_tuples[0][1] == logging.ERROR
    assert "Traceback (most recent call last)" in caplog.record_tuples[0][2]
    assert '"this is some exception"' in caplog.record_tuples[0][2]


def test_production_exception_logging(caplog: LogCaptureFixture) -> None:
    """Test that exceptions are properly logged in the production logger."""
    configure_logging(name="myapp", profile="production", log_level="info")
    logger = structlog.get_logger("myapp")

    try:
        raise ValueError("this is some exception")
    except Exception:
        logger.exception("exception happened", foo="bar")

    assert caplog.record_tuples[0][0] == "myapp"
    assert caplog.record_tuples[0][1] == logging.ERROR
    data = json.loads(caplog.record_tuples[0][2])
    assert data == {
        "event": "exception happened",
        "exception": ANY,
        "foo": "bar",
        "logger": "myapp",
        "severity": "error",
    }
    assert "Traceback (most recent call last)" in data["exception"]
    assert '"this is some exception"' in data["exception"]
