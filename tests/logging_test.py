"""Tests for the safir.logging module."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import structlog

from safir.logging import configure_logging

if TYPE_CHECKING:
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
