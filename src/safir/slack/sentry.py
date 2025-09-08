"""Helpers for Sentry support in SlackExceptions."""

from dataclasses import dataclass, field
from typing import Any

__all__ = ["SentryEventInfo"]


@dataclass
class SentryEventInfo:
    """A collection of metadata to add to Sentry events.

    The overrideable `~SlackException.to_sentry` method returns an object of
    this type.
    """

    tags: dict[str, str] = field(default_factory=dict)
    """Short key-value pairs to add to a Sentry event.

    Use tags for small values that you would like to search by and aggregate
    over when analyzing multiple Sentry events in the Sentry UI.
    """

    contexts: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Detailed information to add to a Sentry event.

    You can not search by context values, but you can store more data in them.
    """

    attachments: dict[str, Any] = field(default_factory=dict)
    """Long strings of text, or other files, to add to a Sentry event.

    Attachments can hold the most text, but are the hardest to view in the
    Sentry UI. They can also hold non-text files.
    """
    username: str | None = None
