"""Tests for datetime utility functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from safir.datetime import current_datetime, isodatetime, parse_isodatetime


def test_current_datetime() -> None:
    time = current_datetime()
    assert time.microsecond == 0
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
