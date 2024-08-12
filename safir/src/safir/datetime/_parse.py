"""Functions to parse dates and times."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_TIMEDELTA_PATTERN = re.compile(
    r"((?P<weeks>\d+?)\s*(weeks|week|w))?\s*"
    r"((?P<days>\d+?)\s*(days|day|d))?\s*"
    r"((?P<hours>\d+?)\s*(hours|hour|hr|h))?\s*"
    r"((?P<minutes>\d+?)\s*(minutes|minute|mins|min|m))?\s*"
    r"((?P<seconds>\d+?)\s*(seconds|second|secs|sec|s))?$"
)
"""Regular expression pattern for a time duration."""

__all__ = [
    "parse_isodatetime",
    "parse_timedelta",
]


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

    If you want to accept strings of this type as input to a
    `~datetime.timedelta` field in a Pydantic model, use the
    `~safir.pydantic.HumanTimedelta` type as the field type. It uses this
    function to parse input strings.

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
    """
    m = _TIMEDELTA_PATTERN.match(text.strip())
    if m is None:
        raise ValueError(f"Could not parse {text!r} as a time duration")
    td_args = {k: int(v) for k, v in m.groupdict().items() if v is not None}
    return timedelta(**td_args)
