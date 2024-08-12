"""Models for structlog-based logging."""

from __future__ import annotations

from enum import Enum
from typing import Any, Self

__all__ = [
    "LogLevel",
    "Profile",
]


class Profile(Enum):
    """Logging profile for the application."""

    production = "production"
    """Log messages in JSON."""

    development = "development"
    """Log messages in a format intended for human readability."""


class LogLevel(Enum):
    """Python logging level.

    Any case variation is accepted when converting a string to an enum value
    via the class constructor.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def _missing_(cls, value: Any) -> Self | None:
        """Allow strings in any case to be used to create the enum."""
        if not isinstance(value, str):
            return None
        value = value.upper()
        for member in cls:
            if member.value == value:
                return member
        return None
