"""Utilities for configuring Alembic to use structlog."""

from __future__ import annotations

import logging
import logging.config

import structlog

from ._models import LogLevel
from ._structlog import add_log_severity

__all__ = ["configure_alembic_logging"]


def configure_alembic_logging(
    log_level: LogLevel | str = LogLevel.INFO,
) -> None:
    """Set up logging for Alembic.

    This configures Alembic to use structlog for output formatting so that its
    logs are also in JSON. This helps Google's Cloud Logging system understand
    the logs.

    Parameters
    ----------
    log_level
        The Python log level. May be given as a `LogLevel` enum (preferred)
        or a case-insensitive string.
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
                "json": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": processors,
                    "foreign_pre_chain": [add_log_severity],
                },
            },
            "handlers": {
                "alembic": {
                    "level": log_level.value,
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "alembic": {
                    "handlers": ["alembic"],
                    "level": log_level.value,
                    "propagate": False,
                },
            },
        }
    )
