"""Utilities for configuring structlog-based logging."""

from __future__ import annotations

import logging
import logging.config
import re
import sys
from enum import Enum
from typing import Any, Optional

import structlog
from structlog.stdlib import add_log_level
from structlog.types import EventDict

__all__ = [
    "LogLevel",
    "Profile",
    "add_log_severity",
    "configure_logging",
    "configure_uvicorn_logging",
    "logger_name",
]

logger_name: Optional[str] = None
"""Name of the configured global logger.

When `configure_logging` is called, the name of the configured logger is
stored in this variable. It is used by the logger dependency to retrieve the
application's configured logger.

Only one configured logger is supported. Additional calls to
`configure_logging` change the stored logger name.
"""

_UVICORN_ACCESS_REGEX = re.compile(r'^[0-9.]+:[0-9]+ - "([^"]+)" ([0-9]+)$')
"""Regex to parse Uvicorn access logs."""


class Profile(Enum):
    """Logging profile for the application."""

    production = "production"
    """Log messages in JSON."""

    development = "development"
    """Log messages in a format intended for human readability."""


class LogLevel(Enum):
    """Python logging level."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


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
    global logger_name
    logger_name = name


def _process_uvicorn_access_log(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Parse a Uvicorn access log entry into key/value pairs.

    Intended for use as a structlog processor.

    This checks whether the log message is a Uvicorn access log entry and, if
    so, parses the message into key/value pairs for JSON logging so that the
    details can be programmatically extracted.  ``remoteIp`` is intentionally
    omitted since it isn't aware of ``X-Forwarded-For`` and will therefore
    always point to an uninteresting in-cluster IP.

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
    EventDict
        The modified `~structlog.types.EventDict` with the added key.
    """
    match = _UVICORN_ACCESS_REGEX.match(event_dict["event"])
    if not match:
        return event_dict
    request = match.group(1)
    method, rest = request.split(" ", 1)
    url, protocol = rest.rsplit(" ", 1)
    if "httpRequest" not in event_dict:
        event_dict["httpRequest"] = {}
    event_dict["httpRequest"]["protocol"] = protocol
    event_dict["httpRequest"]["requestMethod"] = method
    event_dict["httpRequest"]["requestUrl"] = url
    event_dict["httpRequest"]["status"] = match.group(2)
    return event_dict


def configure_uvicorn_logging(
    log_level: LogLevel | str = LogLevel.INFO,
) -> None:
    """Set up logging.

    This configures Uvicorn to use structlog for output formatting and
    installs a custom processor to parse its access log messages into
    additional log context that matches the format of Google log messages.
    This helps Google's Cloud Logging system understand the logs. Access logs
    are sent to standard output and all other logs are sent to standard
    error.

    Parameters
    ----------
    log_level
        The Python log level. May be given as a `LogLevel` enum (preferred)
        or a case-insensitive string.

    Notes
    -----
    This method should normally be called during FastAPI app creation, either
    during Python module import or inside the function that creates and
    returns the FastAPI app that Uvicorn will run. This ensures the logging
    setup is complete before Uvicorn logs its first message.
    """
    if not isinstance(log_level, LogLevel):
        log_level = LogLevel[log_level.upper()]

    processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json-access": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": processors,
                    "foreign_pre_chain": [
                        add_log_severity,
                        _process_uvicorn_access_log,
                    ],
                },
                "json": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": processors,
                    "foreign_pre_chain": [add_log_severity],
                },
            },
            "handlers": {
                "uvicorn.access": {
                    "level": log_level.value,
                    "class": "logging.StreamHandler",
                    "formatter": "json-access",
                    "stream": "ext://sys.stdout",
                },
                "uvicorn.default": {
                    "level": log_level.value,
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                },
            },
            "loggers": {
                "uvicorn.error": {
                    "handlers": ["uvicorn.default"],
                    "level": log_level.value,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["uvicorn.access"],
                    "level": log_level.value,
                    "propagate": False,
                },
            },
        }
    )
