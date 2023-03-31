"""Date and time manipulation utility functions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import overload

__all__ = [
    "current_datetime",
    "format_datetime_for_logging",
    "isodatetime",
    "parse_isodatetime",
]


def current_datetime(*, microseconds: bool = False) -> datetime:
    """Construct a `~datetime.datetime` for the current time.

    It's easy to forget to force all `~datetime.datetime` objects to be time
    zone aware. This function forces UTC for all objects.

    Databases do not always store microseconds in time fields, and having some
    dates with microseconds and others without them can lead to bugs, so by
    default it suppresses the microseconds.

    Parameters
    ----------
    microseconds
        Whether to include microseconds. Consider setting this to `True` when
        getting timestamps for error reporting, since granular timestamps can
        help in understanding sequencing.

    Returns
    -------
    datetime.datetime
        The current time forced to UTC and optionally with the microseconds
        field zeroed.
    """
    result = datetime.now(tz=timezone.utc)
    if microseconds:
        return result
    else:
        return result.replace(microsecond=0)


@overload
def format_datetime_for_logging(timestamp: datetime) -> str:
    ...


@overload
def format_datetime_for_logging(timestamp: None) -> None:
    ...


def format_datetime_for_logging(timestamp: datetime | None) -> str | None:
    """Format a datetime for logging and human readabilty.

    Parameters
    ----------
    timestamp
        Object to format. Must be in UTC or timezone-naive (in which case it's
        assumed to be in UTC).

    Returns
    -------
    str or None
        The datetime in format ``YYYY-MM-DD HH:MM:SS[.sss]`` with milliseconds
        added if and only if the microseconds portion of ``timestamp`` is not
        0. There will be no ``T`` separator or time zone information.

    Raises
    ------
    ValueError
        Raised if the argument is in a time zone other than UTC.
    """
    if timestamp:
        if timestamp.tzinfo not in (None, timezone.utc):
            raise ValueError("Datetime {timestamp} not in UTC")
        if timestamp.microsecond:
            result = timestamp.isoformat(sep=" ", timespec="milliseconds")
        else:
            result = timestamp.isoformat(sep=" ", timespec="seconds")
        return result.split("+")[0]
    else:
        return None


def isodatetime(timestamp: datetime) -> str:
    """Format a timestamp in UTC in a standard ISO date format.

    Parameters
    ----------
    timestamp
        Date and time to format.

    Returns
    -------
    str
        Date and time formatted as an ISO 8601 date and time using ``Z`` as
        the time zone.  This format is compatible with both Kubernetes and the
        IVOA UWS standard.

    Raises
    ------
    ValueError
        The provided timestamp was not in UTC.
    """
    if timestamp.tzinfo not in (None, timezone.utc):
        raise ValueError("Datetime {timestamp} not in UTC")
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_isodatetime(time_string: str) -> datetime | None:
    """Parse a string in a standard ISO date format.

    Parameters
    ----------
    time_string
        Date and time formatted as an ISO 8601 date and time using ``Z`` as
        the time zone.  This is the same format produced by `isodatetime` and
        is compatible with Kubernetes and the IVOA UWS standard.

    Returns
    -------
    datetime.datetime
        The corresponding `datetime.datetime`.

    Raises
    ------
    ValueError
        The provided ``time_string`` is not in the correct format.

    Notes
    -----
    When parsing input for a model, use `safir.pydantic.normalize_isodatetime`
    instead of this function.  Using a model will be the normal case; this
    function is primarily useful in tests.
    """
    if not time_string.endswith("Z"):
        raise ValueError(f"{time_string} does not end with Z")
    return datetime.fromisoformat(time_string[:-1] + "+00:00")
