"""Tests for Pydantic utility functions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from pydantic import BaseModel, ValidationError, root_validator

from safir.pydantic import (
    CamelCaseModel,
    normalize_datetime,
    normalize_isodatetime,
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


def test_normalize_isodatetime() -> None:
    assert normalize_isodatetime(None) is None

    date = datetime.fromisoformat("2023-01-25T15:44:34+00:00")
    assert date == normalize_isodatetime("2023-01-25T15:44:34Z")

    date = datetime.fromisoformat("2023-01-25T15:44:00+00:00")
    assert date == normalize_isodatetime("2023-01-25T15:44Z")

    with pytest.raises(ValueError):
        normalize_isodatetime("2023-01-25T15:44:00+00:00")

    with pytest.raises(ValueError):
        normalize_isodatetime(1668814932)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        normalize_isodatetime("next thursday")


def test_to_camel_case() -> None:
    assert to_camel_case("foo") == "foo"
    assert to_camel_case("minimum_lifetime") == "minimumLifetime"
    assert to_camel_case("replace_403") == "replace403"
    assert to_camel_case("foo_bar_baz") == "fooBarBaz"


def test_camel_case_model() -> None:
    class TestModel(CamelCaseModel):
        minimum_lifetime: int
        replace_403: bool
        foo_bar_baz: str

    camel = {
        "minimumLifetime": 10,
        "replace403": False,
        "fooBarBaz": "something",
    }
    snake = {
        "minimum_lifetime": 10,
        "replace_403": False,
        "foo_bar_baz": "something",
    }
    data = TestModel.parse_obj(camel)
    assert data.minimum_lifetime == 10
    assert not data.replace_403
    assert data.foo_bar_baz == "something"
    assert data.dict() == camel
    assert data.dict(by_alias=False) == snake
    assert data.json() == json.dumps(camel)
    assert data.json(by_alias=False) == json.dumps(snake)

    snake_data = TestModel.parse_obj(snake)
    assert data.minimum_lifetime == 10
    assert not data.replace_403
    assert data.foo_bar_baz == "something"
    assert snake_data.dict() == data.dict()
    assert snake_data.json() == data.json()


def test_validate_exactly_one_of() -> None:
    class Model(BaseModel):
        foo: Optional[int] = None
        bar: Optional[int] = None
        baz: Optional[int] = None

        _validate_type = root_validator(allow_reuse=True)(
            validate_exactly_one_of("foo", "bar", "baz")
        )

    Model.parse_obj({"foo": 4, "bar": None})
    Model.parse_obj({"baz": 4})
    Model.parse_obj({"bar": 4})
    Model.parse_obj({"foo": None, "bar": 4})

    with pytest.raises(ValidationError) as excinfo:
        Model.parse_obj({"foo": 4, "bar": 3, "baz": None})
    assert "only one of foo, bar, and baz may be given" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        Model.parse_obj({"foo": None, "baz": None})
    assert "one of foo, bar, and baz must be given" in str(excinfo.value)

    class TwoModel(BaseModel):
        foo: Optional[int] = None
        bar: Optional[int] = None

        _validate_type = root_validator(allow_reuse=True)(
            validate_exactly_one_of("foo", "bar")
        )

    with pytest.raises(ValidationError) as excinfo:
        TwoModel.parse_obj({"foo": 3, "bar": 4})
    assert "only one of foo and bar may be given" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        TwoModel.parse_obj({})
    assert "one of foo and bar must be given" in str(excinfo.value)
