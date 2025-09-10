"""Functions to get the current date and time."""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["current_datetime"]


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
    result = datetime.now(tz=UTC)
    if microseconds:
        return result
    else:
        return result.replace(microsecond=0)
