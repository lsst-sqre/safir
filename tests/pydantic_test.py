"""Tests for Pydantic utility functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from safir.pydantic import (
    normalize_datetime,
    to_camel_case,
    validate_exactly_one_of,
)


def test_normalize_datetime() -> None:
    assert normalize_datetime(None) is None

    date = datetime.fromtimestamp(1668814932, tz=timezone.utc)
    assert normalize_datetime(1668814932) == date

    mst_zone = timezone(-timedelta(hours=7))
    mst_date = datetime.now(tz=mst_zone)
    utc_date = mst_date.astimezone(timezone.utc)
    assert normalize_datetime(mst_date) == utc_date

    naive_date = datetime.utcnow()
    aware_date = normalize_datetime(naive_date)
    assert aware_date == naive_date.replace(tzinfo=timezone.utc)
    assert aware_date.tzinfo == timezone.utc


def test_to_camel_case() -> None:
    assert to_camel_case("foo") == "foo"
    assert to_camel_case("minimum_lifetime") == "minimumLifetime"
    assert to_camel_case("replace_403") == "replace403"
    assert to_camel_case("foo_bar_baz") == "fooBarBaz"


def test_validate_exactly_one_of() -> None:
    values = {"foo": 4, "bar": None}
    validate_exactly_one_of("foo", "bar")(None, values)

    values = {"foo": 4}
    validate_exactly_one_of("foo", "bar", "baz")(None, values)

    validate_exactly_one_of("foo", "bar")(4, {})
    validate_exactly_one_of("foo", "bar")(4, {"foo": None})

    with pytest.raises(ValueError) as excinfo:
        validate_exactly_one_of("foo", "bar")(3, values)
    assert "only one of foo and bar may be given" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        validate_exactly_one_of("foo", "bar")(None, {})
    assert "one of foo and bar must be given" in str(excinfo.value)

    values = {"foo": 4, "bar": 3}
    with pytest.raises(ValueError) as excinfo:
        validate_exactly_one_of("foo", "bar", "baz")(None, values)
    assert "only one of foo, bar, and baz may be given" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        validate_exactly_one_of("foo", "bar", "baz")(None, {"foo": None})
    assert "one of foo, bar, and baz must be given" in str(excinfo.value)
