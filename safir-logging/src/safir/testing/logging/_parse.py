"""Helper functions for testing logging."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from logging import getLevelName
from typing import Any

__all__ = ["parse_log_tuples"]


def _assert_timestamp_recent(isotimestamp: str, now: datetime) -> None:
    """Assert if a timestamp is malformed or older than 10 seconds."""
    if not isotimestamp.endswith("Z"):
        raise AssertionError(f'"{isotimestamp}".endswith("Z")')
    timestamp = datetime.fromisoformat(isotimestamp[:-1]).replace(tzinfo=UTC)
    if not (now - timedelta(hours=1) < timestamp < now):
        msg = f"{isotimestamp} within 1 hour of {now!s}"
        raise AssertionError(msg)


def parse_log_tuples(
    logger_name: str,
    record_tuples: Iterable[tuple[str, int, str]],
    *,
    ignore_debug: bool = False,
) -> list[dict[str, Any]]:
    """Parse JSON log record tuples into structured data.

    This function is intended for use in test suites that want to check the
    messages logged via structlog_ in the Safir production profile, meaning
    that each log message is in JSON. The message bodies are parsed, checked
    to ensure they're logged with the provided logger name, stripped of
    uninteresting data after verification (any timestamp, ``request_id``, or
    HTTP user agent, all of which vary in uninteresting ways), and then
    returned as structured records.

    Any timestamp in the log message is expected to be within 10 seconds of
    the current time.

    Parameters
    ----------
    logger_name
        Only look at messages logged by this logger. Any messages from a
        different logger will be ignored. The logger is removed from the
        message before returning it.
    record_tuples
        Tuples of log records consisting of logger name, log level, and
        message. Normally this argument should be ``caplog.record_tuples``,
        provided by the pytest ``caplog`` fixture.
    ignore_debug
        If set to `True`, filter out all debug messages.

    Returns
    -------
    list of dict
        List of parsed JSON dictionaries with the common log attributes
        removed (after validation).

    Raises
    ------
    AssertionError
        Raised if any of the validation of the log messages fails.
    """
    now = datetime.now(tz=UTC)
    messages = []

    for name, level, message_raw in record_tuples:
        message = json.loads(message_raw)

        if name != logger_name:
            continue
        if message["logger"] != logger_name:
            msg = f"logger {message['logger']} == {logger_name}"
            raise AssertionError(msg)
        del message["logger"]

        level_name = getLevelName(level).lower()
        if message["severity"] != level_name:
            msg = f"severity {message['severity']} == {level}"
            raise AssertionError(msg)

        if "timestamp" in message:
            _assert_timestamp_recent(message["timestamp"], now)
            del message["timestamp"]

        if "request_id" in message:
            del message["request_id"]
            if "userAgent" in message["httpRequest"]:
                del message["httpRequest"]["userAgent"]

        if not ignore_debug or message["severity"] != "debug":
            messages.append(message)

    return messages
