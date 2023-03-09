"""Tests for datetime utility functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from safir.datetime import (
    current_datetime,
    format_datetime_for_logging,
    isodatetime,
    parse_isodatetime,
)


def test_current_datetime() -> None:
    time = current_datetime()
    assert time.microsecond == 0
    assert time.tzinfo == timezone.utc
    now = datetime.now(tz=timezone.utc)
    assert now - timedelta(seconds=2) <= time <= now

    time = current_datetime(microseconds=True)
    if not time.microsecond:
        time = current_datetime(microseconds=True)
    assert time.microsecond != 0
    assert time.tzinfo == timezone.utc
    now = datetime.now(tz=timezone.utc)
    assert now - timedelta(seconds=2) <= time <= now


def test_isodatetime() -> None:
    time = datetime.fromisoformat("2022-09-16T12:03:45+00:00")
    assert isodatetime(time) == "2022-09-16T12:03:45Z"

    with pytest.raises(ValueError):
        isodatetime(datetime.fromisoformat("2022-09-16T12:03:45+02:00"))


def test_parse_isodatetime() -> None:
    time = parse_isodatetime("2022-09-16T12:03:45Z")
    assert time == datetime(2022, 9, 16, 12, 3, 45, tzinfo=timezone.utc)
    now = current_datetime()
    assert parse_isodatetime(isodatetime(now)) == now

    with pytest.raises(ValueError):
        parse_isodatetime("2022-09-16T12:03:45+00:00")


def test_format_datetime_for_logging() -> None:
    time = datetime.fromisoformat("2022-09-16T12:03:45+00:00")
    assert format_datetime_for_logging(time) == "2022-09-16 12:03:45"

    # Test with milliseconds, allowing for getting extremely unlucky and
    # having no microseconds. Getting unlucky twice seems impossible, so we'll
    # fail in that case rather than loop.
    now = datetime.now(tz=timezone.utc)
    if not now.microsecond:
        now = datetime.now(tz=timezone.utc)
    milliseconds = int(now.microsecond / 1000)
    expected = now.strftime("%Y-%m-%d %H:%M:%S") + f".{milliseconds:03n}"
    assert format_datetime_for_logging(now) == expected

    time = datetime.now(tz=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError):
        format_datetime_for_logging(time)
