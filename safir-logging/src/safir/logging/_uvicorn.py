"""Utilities for configuring uvicorn to use structlog."""

from __future__ import annotations

import logging
import logging.config
import re

import structlog
from structlog.types import EventDict

from ._models import LogLevel
from ._structlog import add_log_severity

__all__ = ["configure_uvicorn_logging"]

_UVICORN_ACCESS_REGEX = re.compile(r'^[0-9.]+:[0-9]+ - "([^"]+)" ([0-9]+)$')
"""Regex to parse Uvicorn access logs."""


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
