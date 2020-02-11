"""Utilities for configuring structlog-based logging.
"""

__all__ = ["configure_logging"]

import logging
import sys

import structlog


def configure_logging(
    *, name: str, profile: str = "production", log_level: str = "info"
) -> None:
    """Configure logging and structlog.

    Parameters
    ----------
    name : `str`
        Name of the logger, which is typically the name of your application's
        root namespace.
    profile : `str`
        The name of the application profile:

        development
            Log messages are formatted for easier reading on the terminal.
        production
            Log messages are formatted as JSON objects.
    log_level : `str`
        The log level, in string form:

        - ``DEBUG``
        - ``INFO``
        - ``WARNINGS``
        - ``ERROR``

    Notes
    -----
    This function helps you configure a useful logging set up for your
    application that's based on `structlog <http://www.structlog.org>`__.

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
       "level": "info"}

    Examples
    --------
    .. code-block:: python

       import structlog
       from safir.logging import configure_logging


       configure_logging(name="mybot")
       logger = structlog.get_logger("mybot")
       logger.info("Hello world")
    """
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(name)
    logger.addHandler(stream_handler)
    logger.setLevel(log_level.upper())

    if profile == "production":
        # JSON-formatted logging
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Key-value formatted logging
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
