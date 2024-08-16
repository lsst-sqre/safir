"""Utilities for configuring structlog-based logging."""

from __future__ import annotations

import logging
import logging.config
import sys
from typing import Any

import structlog
from structlog.stdlib import add_log_level
from structlog.types import EventDict

try:
    from safir.dependencies import logger as logger_dependency

    _UPDATE_DEPENDENCY = True
except Exception:
    _UPDATE_DEPENDENCY = False

from ._models import LogLevel, Profile

__all__ = [
    "add_log_severity",
    "configure_logging",
]


def add_log_severity(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add the log level to the event dict as ``severity``.

    Intended for use as a structlog processor.

    This is the same as `structlog.stdlib.add_log_level` except that it
    uses the ``severity`` key rather than ``level`` for compatibility with
    Google Log Explorer and its automatic processing of structured logs.

    Parameters
    ----------
    logger
        The wrapped logger object.
    method_name
        The name of the wrapped method (``warning`` or ``error``, for
        example).
    event_dict
        Current context and current event. This parameter is also modified in
        place, matching the normal behavior of structlog processors.

    Returns
    -------
    ``structlog.types.EventDict``
        The modified ``structlog.types.EventDict`` with the added key.
    """
    severity = add_log_level(logger, method_name, {})["level"]
    event_dict["severity"] = severity
    return event_dict


def configure_logging(
    *,
    name: str,
    profile: Profile | str = Profile.production,
    log_level: LogLevel | str = LogLevel.INFO,
    add_timestamp: bool = False,
) -> None:
    """Configure logging and structlog.

    Parameters
    ----------
    name
        Name of the logger, which is typically the name of your application's
        root namespace.
    profile
        The name of the application profile:

        development
            Log messages are formatted for easier reading on the terminal.
        production
            Log messages are formatted as JSON objects.

        May be given as a `Profile` enum value (preferred) or a string.
    log_level
        The Python log level. May be given as a `LogLevel` enum (preferred)
        or a case-insensitive string.
    add_timestamp
        Whether to add an ISO-format timestamp to each log message.

    Notes
    -----
    This function helps you configure a useful logging set up for your
    application that's based on structlog_.

    First, it configures the logger for your application to log to STDOUT.
    Second, it configures the formatting of your log messages through
    structlog.

    In development mode, messages are key-value formatted, like this:

    .. code-block:: text

       [info     ] Hello world                    [myapp] answer=42

    Here, "Hello world" is the message. ``answer=42`` is a value bound to the
    logger.

    In production mode, messages are formatted as JSON objects:

    .. code-block:: text

       {"answer": 42, "event": "Hello world", "logger": "myapp",
       "severity": "info"}

    Examples
    --------
    .. code-block:: python

       import structlog
       from safir.logging import configure_logging


       configure_logging(name="mybot")
       logger = structlog.get_logger("mybot")
       logger.info("Hello world")
    """
    if not isinstance(log_level, LogLevel):
        log_level = LogLevel[log_level.upper()]
    if not isinstance(profile, Profile):
        profile = Profile[profile]

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(name)
    logger.handlers = []
    logger.addHandler(stream_handler)
    logger.setLevel(log_level.value)

    processors: list[Any] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
    ]
    if add_timestamp:
        processors.append(structlog.processors.TimeStamper(fmt="iso"))
    processors.extend(
        [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
        ]
    )
    if profile == Profile.production:
        # JSON-formatted logging
        processors.append(add_log_severity)
        processors.append(structlog.processors.format_exc_info)
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Key-value formatted logging
        processors.append(structlog.stdlib.add_log_level)
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Set the configured name for the global logger.
    if _UPDATE_DEPENDENCY:
        logger_dependency._logger_name = name  # noqa: SLF001
