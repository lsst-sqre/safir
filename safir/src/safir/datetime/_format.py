"""Functions to format dates and times."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import overload

__all__ = [
    "format_datetime_for_logging",
    "isodatetime",
]


@overload
def format_datetime_for_logging(timestamp: datetime) -> str: ...


@overload
def format_datetime_for_logging(timestamp: None) -> None: ...


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
        if timestamp.utcoffset() != timedelta(seconds=0):
            raise ValueError(f"datetime {timestamp} not in UTC")
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
    if timestamp.utcoffset() != timedelta(seconds=0):
        raise ValueError(f"datetime {timestamp} not in UTC")
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
