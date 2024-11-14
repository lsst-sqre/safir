"""Tests for datetime utility functions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

from safir.datetime import (
    current_datetime,
    format_datetime_for_logging,
    isodatetime,
    parse_isodatetime,
    parse_timedelta,
)


def test_current_datetime() -> None:
    time = current_datetime()
    assert time.microsecond == 0
    assert time.tzinfo == UTC
    now = datetime.now(tz=UTC)
    assert now - timedelta(seconds=2) <= time <= now

    time = current_datetime(microseconds=True)
    if not time.microsecond:
        time = current_datetime(microseconds=True)
    assert time.microsecond != 0
    assert time.tzinfo == UTC
    now = datetime.now(tz=UTC)
    assert now - timedelta(seconds=2) <= time <= now


def test_isodatetime() -> None:
    time = datetime.fromisoformat("2022-09-16T12:03:45+00:00")
    assert isodatetime(time) == "2022-09-16T12:03:45Z"

    with pytest.raises(ValueError, match=r"datetime .* not in UTC"):
        isodatetime(datetime.fromisoformat("2022-09-16T12:03:45+02:00"))

    # Pydantic's JSON decoder uses a TzInfo data structure instead of
    # datetime.timezone.utc. Make sure that's still recognized as UTC.
    class Test(BaseModel):
        time: datetime

    json_model = Test(time=time).model_dump_json()
    model = Test.model_validate_json(json_model)
    assert isodatetime(model.time) == "2022-09-16T12:03:45Z"


def test_parse_isodatetime() -> None:
    time = parse_isodatetime("2022-09-16T12:03:45Z")
    assert time == datetime(2022, 9, 16, 12, 3, 45, tzinfo=UTC)
    now = current_datetime()
    assert parse_isodatetime(isodatetime(now)) == now
    time = parse_isodatetime("2022-09-16T12:03:45")
    assert time == datetime(2022, 9, 16, 12, 3, 45, tzinfo=UTC)
    time = parse_isodatetime("2022-09-16")
    assert time == datetime(2022, 9, 16, 0, 0, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="does not match IVOA format"):
        parse_isodatetime("2022-09-16T12:03:45+00:00")


def test_format_datetime_for_logging() -> None:
    time = datetime.fromisoformat("2022-09-16T12:03:45+00:00")
    assert format_datetime_for_logging(time) == "2022-09-16 12:03:45"

    # Test with milliseconds, allowing for getting extremely unlucky and
    # having no microseconds. Getting unlucky twice seems impossible, so we'll
    # fail in that case rather than loop.
    now = datetime.now(tz=UTC)
    if not now.microsecond:
        now = datetime.now(tz=UTC)
    milliseconds = int(now.microsecond / 1000)
    expected = now.strftime("%Y-%m-%d %H:%M:%S") + f".{milliseconds:03n}"
    assert format_datetime_for_logging(now) == expected

    time = datetime.now(tz=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError, match=r"datetime .* not in UTC"):
        format_datetime_for_logging(time)

    # Pydantic's JSON decoder uses a TzInfo data structure instead of
    # datetime.timezone.utc. Make sure that's still recognized as UTC.
    class Test(BaseModel):
        time: datetime

    json_model = Test(time=now).model_dump_json()
    model = Test.model_validate_json(json_model)
    assert format_datetime_for_logging(model.time) == expected


def test_parse_timdelta() -> None:
    assert parse_timedelta("8d") == timedelta(days=8)
    assert parse_timedelta("4h 3minutes\n") == timedelta(hours=4, minutes=3)
    assert parse_timedelta("\n 5w4d") == timedelta(weeks=5, days=4)
    assert parse_timedelta(
        "2weeks 2days 2hours 2minutes 2seconds"
    ) == timedelta(weeks=2, days=2, hours=2, minutes=2, seconds=2)
    assert parse_timedelta("1week 1day 1hour 1minute 1second") == timedelta(
        weeks=1, days=1, hours=1, minutes=1, seconds=1
    )
    assert parse_timedelta("4hr 5mins 6secs") == timedelta(
        hours=4, minutes=5, seconds=6
    )
    assert parse_timedelta("17min 65sec") == timedelta(minutes=17, seconds=65)

    with pytest.raises(ValueError, match="Could not parse"):
        parse_timedelta("3s4m")
    with pytest.raises(ValueError, match="Could not parse"):
        parse_timedelta("4weeks 36ms")
