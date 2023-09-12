"""Tests for Pydantic utility functions."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError, model_validator

from safir.pydantic import (
    CamelCaseModel,
    normalize_datetime,
    normalize_isodatetime,
    to_camel_case,
    validate_exactly_one_of,
)


def test_normalize_datetime() -> None:
    assert normalize_datetime(None) is None

    date = datetime.fromtimestamp(1668814932, tz=UTC)
    assert normalize_datetime(1668814932) == date

    mst_zone = timezone(-timedelta(hours=7))
    mst_date = datetime.now(tz=mst_zone)
    utc_date = mst_date.astimezone(UTC)
    assert normalize_datetime(mst_date) == utc_date

    naive_date = datetime.utcnow()  # noqa: DTZ003
    aware_date = normalize_datetime(naive_date)
    assert aware_date == naive_date.replace(tzinfo=UTC)
    assert aware_date.tzinfo == UTC


def test_normalize_isodatetime() -> None:
    assert normalize_isodatetime(None) is None

    date = datetime.fromisoformat("2023-01-25T15:44:34+00:00")
    assert date == normalize_isodatetime("2023-01-25T15:44:34Z")

    date = datetime.fromisoformat("2023-01-25T15:44:00+00:00")
    assert date == normalize_isodatetime("2023-01-25T15:44Z")

    with pytest.raises(ValueError, match=r"Must be a string in .* format"):
        normalize_isodatetime("2023-01-25T15:44:00+00:00")

    with pytest.raises(ValueError, match=r"Must be a string in .* format"):
        normalize_isodatetime(1668814932)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=r"Must be a string in .* format"):
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
    data = TestModel.model_validate(camel)
    assert data.minimum_lifetime == 10
    assert not data.replace_403
    assert data.foo_bar_baz == "something"
    assert data.model_dump() == camel
    assert data.model_dump(by_alias=False) == snake
    assert json.loads(data.model_dump_json()) == camel
    assert json.loads(data.model_dump_json(by_alias=False)) == snake

    snake_data = TestModel.model_validate(snake)
    assert data.minimum_lifetime == 10
    assert not data.replace_403
    assert data.foo_bar_baz == "something"
    assert snake_data.model_dump() == data.model_dump()
    assert snake_data.model_dump_json() == data.model_dump_json()


def test_validate_exactly_one_of() -> None:
    class Model(BaseModel):
        foo: int | None = None
        bar: int | None = None
        baz: int | None = None

        _validate_type = model_validator(mode="after")(
            validate_exactly_one_of("foo", "bar", "baz")
        )

    Model.model_validate({"foo": 4, "bar": None})
    Model.model_validate({"baz": 4})
    Model.model_validate({"bar": 4})
    Model.model_validate({"foo": None, "bar": 4})

    with pytest.raises(ValidationError) as excinfo:
        Model.model_validate({"foo": 4, "bar": 3, "baz": None})
    assert "only one of foo, bar, and baz may be given" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        Model.model_validate({"foo": None, "baz": None})
    assert "one of foo, bar, and baz must be given" in str(excinfo.value)

    class TwoModel(BaseModel):
        foo: int | None = None
        bar: int | None = None

        _validate_type = model_validator(mode="after")(
            validate_exactly_one_of("foo", "bar")
        )

    with pytest.raises(ValidationError) as excinfo:
        TwoModel.model_validate({"foo": 3, "bar": 4})
    assert "only one of foo and bar may be given" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        TwoModel.model_validate({})
    assert "one of foo and bar must be given" in str(excinfo.value)
