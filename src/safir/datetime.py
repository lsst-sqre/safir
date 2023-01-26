"""Date and time manipulation utility functions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

__all__ = [
    "current_datetime",
    "isodatetime",
    "parse_isodatetime",
]


def current_datetime() -> datetime:
    """Construct a `~datetime.datetime` for the current time.

    Databases do not always store microseconds in time fields, and having some
    dates with microseconds and others without them can lead to bugs.  It's
    also easy to forget to force all `~datetime.datetime` objects to be time
    zone aware.  This function avoids both problems by forcing UTC and forcing
    microseconds to 0.

    Returns
    -------
    datetime.datetime
        The current time forced to UTC and with the microseconds field zeroed.
    """
    return datetime.now(tz=timezone.utc).replace(microsecond=0)


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


def parse_isodatetime(time_string: str) -> Optional[datetime]:
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
