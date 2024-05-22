"""Date and time manipulation utility functions."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import overload

_TIMEDELTA_PATTERN = re.compile(
    r"((?P<weeks>\d+?)\s*(weeks|week|w))?\s*"
    r"((?P<days>\d+?)\s*(days|day|d))?\s*"
    r"((?P<hours>\d+?)\s*(hours|hour|hr|h))?\s*"
    r"((?P<minutes>\d+?)\s*(minutes|minute|mins|min|m))?\s*"
    r"((?P<seconds>\d+?)\s*(seconds|second|secs|sec|s))?$"
)
"""Regular expression pattern for a time duration."""

__all__ = [
    "current_datetime",
    "format_datetime_for_logging",
    "isodatetime",
    "parse_isodatetime",
    "parse_timedelta",
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
    result = datetime.now(tz=UTC)
    if microseconds:
        return result
    else:
        return result.replace(microsecond=0)


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


def parse_isodatetime(time_string: str) -> datetime:
    """Parse a string in a standard ISO date format.

    Parameters
    ----------
    time_string
        Date and time formatted as an ISO 8601 date and time using ``Z`` as
        the time zone. This is the same format produced by `isodatetime` and
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
    instead of this function. Using a model will be the normal case; this
    function is primarily useful in tests or for the special parsing cases
    required by the IVOA UWS standard.
    """
    if not time_string.endswith("Z"):
        raise ValueError(f"{time_string} does not end with Z")
    return datetime.fromisoformat(time_string[:-1] + "+00:00")


def parse_timedelta(text: str) -> timedelta:
    """Parse a string into a `datetime.timedelta`.

    Expects a string consisting of one or more sequences of numbers and
    duration abbreviations, separated by optional whitespace. Whitespace at
    the beginning and end of the string is ignored. The supported
    abbreviations are:

    - Week: ``weeks``, ``week``, ``w``
    - Day: ``days``, ``day``, ``d``
    - Hour: ``hours``, ``hour``, ``hr``, ``h``
    - Minute: ``minutes``, ``minute``, ``mins``, ``min``, ``m``
    - Second: ``seconds``, ``second``, ``secs``, ``sec``, ``s``

    If several are present, they must be given in the above order. Example
    valid strings are ``8d`` (8 days), ``4h 3minutes`` (four hours and three
    minutes), and ``5w4d`` (five weeks and four days).

    This function can be as a before-mode validator for Pydantic
    `~datetime.timedelta` fields, replacing Pydantic's default ISO 8601
    duration support.

    Parameters
    ----------
    text
        Input string.

    Returns
    -------
    datetime.timedelta
        Converted `datetime.timedelta`.

    Raises
    ------
    ValueError
        Raised if the string is not in a valid format.

    Examples
    --------
    To accept a `~datetime.timedelta` in this format in a Pydantic model, use
    a Pydantic field validator such as the following:

    .. code-block:: python

       @field_validator("lifetime", mode="before")
       @classmethod
       def _validate_lifetime(
           cls, v: str | float | timedelta
       ) -> float | timedelta:
           if not isinstance(v, str):
               return v
           return parse_timedelta(v)

    This will disable the Pydantic support for ISO 8601 durations and expect
    the format parsed by this function instead.
    """
    m = _TIMEDELTA_PATTERN.match(text.strip())
    if m is None:
        raise ValueError(f"Could not parse {text!r} as a time duration")
    td_args = {k: int(v) for k, v in m.groupdict().items() if v is not None}
    return timedelta(**td_args)
