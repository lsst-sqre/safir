"""datetime management for databases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import overload

__all__ = [
    "datetime_from_db",
    "datetime_to_db",
]


@overload
def datetime_from_db(time: datetime) -> datetime: ...


@overload
def datetime_from_db(time: None) -> None: ...


def datetime_from_db(time: datetime | None) -> datetime | None:
    """Add the UTC time zone to a naive datetime from the database.

    Parameters
    ----------
    time
        The naive datetime from the database, or `None`.

    Returns
    -------
    datetime.datetime or None
        `None` if the input was none, otherwise a timezone-aware version of
        the same `~datetime.datetime` in the UTC timezone.
    """
    if not time:
        return None
    if time.tzinfo not in (None, UTC):
        raise ValueError(f"datetime {time} not in UTC")
    return time.replace(tzinfo=UTC)


@overload
def datetime_to_db(time: datetime) -> datetime: ...


@overload
def datetime_to_db(time: None) -> None: ...


def datetime_to_db(time: datetime | None) -> datetime | None:
    """Strip time zone for storing a datetime in the database.

    Parameters
    ----------
    time
        The timezone-aware `~datetime.datetime` in the UTC time zone, or
        `None`.

    Returns
    -------
    datetime.datetime or None
        `None` if the input was `None`, otherwise the same
        `~datetime.datetime` but timezone-naive and thus suitable for storing
        in a SQL database.
    """
    if not time:
        return None
    if time.utcoffset() != timedelta(seconds=0):
        raise ValueError(f"datetime {time} not in UTC")
    return time.replace(tzinfo=None)
