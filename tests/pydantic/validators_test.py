"""Tests for Pydantic validators."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import (
    BaseModel,
    ValidationError,
    field_validator,
    model_validator,
)

from safir.pydantic import (
    normalize_datetime,
    normalize_isodatetime,
    validate_exactly_one_of,
)


@pytest.mark.filterwarnings("ignore:.*datetime.utcnow.*:DeprecationWarning")
def test_normalize_datetime() -> None:
    class TestModel(BaseModel):
        time: datetime | None

        _val = field_validator("time", mode="before")(normalize_datetime)

    assert TestModel(time=None).time is None

    date = datetime.fromtimestamp(1668814932, tz=UTC)
    model = TestModel.model_validate({"time": 1668814932})
    assert model.time == date

    mst_zone = timezone(-timedelta(hours=7))
    mst_date = datetime.now(tz=mst_zone)
    utc_date = mst_date.astimezone(UTC)
    assert TestModel(time=mst_date).time == utc_date

    naive_date = datetime.fromisoformat("2026-02-26T09:27:43")
    assert naive_date.tzinfo is None
    aware_date = TestModel(time=naive_date).time
    assert aware_date == naive_date.replace(tzinfo=UTC)
    assert aware_date.tzinfo == UTC

    with pytest.raises(ValueError, match=r"Must be a datetime or seconds .*"):
        TestModel.model_validate({"time": "2023-01-25T15:44:00+00:00"})


def test_normalize_isodatetime() -> None:
    class TestModel(BaseModel):
        time: datetime | None

        _val = field_validator("time", mode="before")(normalize_isodatetime)

    assert TestModel(time=None).time is None

    date = datetime.fromisoformat("2023-01-25T15:44:34+00:00")
    model = TestModel.model_validate({"time": "2023-01-25T15:44:34Z"})
    assert model.time == date

    date = datetime.fromisoformat("2023-01-25T15:44:00+00:00")
    model = TestModel.model_validate({"time": "2023-01-25T15:44:00"})
    assert model.time == date

    date = datetime.fromisoformat("2023-01-25").replace(tzinfo=UTC)
    assert TestModel.model_validate({"time": "2023-01-25"}).time == date

    with pytest.raises(ValidationError, match="does not match IVOA format"):
        TestModel.model_validate({"time": "2023-01-25T15:44:00+00:00"})

    with pytest.raises(ValidationError, match="Must be a string in"):
        TestModel.model_validate({"time": 1668814932})

    with pytest.raises(ValidationError, match="does not match IVOA format"):
        TestModel.model_validate({"time": "1668814932"})


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
