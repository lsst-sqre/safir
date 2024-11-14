"""Tests for Pydantic utility functions."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import (
    BaseModel,
    ValidationError,
    field_validator,
    model_validator,
)

from safir.pydantic import (
    CamelCaseModel,
    EnvAsyncPostgresDsn,
    EnvRedisDsn,
    HumanTimedelta,
    IvoaIsoDatetime,
    SecondsTimedelta,
    UtcDatetime,
    normalize_datetime,
    normalize_isodatetime,
    to_camel_case,
    validate_exactly_one_of,
)


def test_env_async_postgres_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    class TestModel(BaseModel):
        dsn: EnvAsyncPostgresDsn

    monkeypatch.delenv("POSTGRES_5432_TCP_PORT", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    model = TestModel.model_validate(
        {"dsn": "postgresql://localhost:7777/some-database"}
    )
    assert model.dsn.scheme == "postgresql"
    assert not model.dsn.username
    assert not model.dsn.password
    assert model.dsn.host == "localhost"
    assert model.dsn.port == 7777
    assert model.dsn.path == "/some-database"
    assert not model.dsn.query

    model = TestModel.model_validate(
        {
            "dsn": (
                "postgresql+asyncpg://user:password@localhost/other"
                "?connect_timeout=10"
            )
        }
    )
    assert model.dsn.scheme == "postgresql+asyncpg"
    assert model.dsn.username == "user"
    assert model.dsn.password == "password"
    assert model.dsn.host == "localhost"
    assert not model.dsn.port
    assert model.dsn.path == "/other"
    assert model.dsn.query == "connect_timeout=10"

    monkeypatch.setenv("POSTGRES_5432_TCP_PORT", "8999")
    model = TestModel.model_validate(
        {
            "dsn": (
                "postgresql://user:password@localhost/other?connect_timeout=10"
            )
        }
    )
    assert model.dsn.scheme == "postgresql"
    assert model.dsn.username == "user"
    assert model.dsn.password == "password"
    assert model.dsn.host == "localhost"
    assert model.dsn.port == 8999
    assert model.dsn.path == "/other"
    assert model.dsn.query == "connect_timeout=10"

    monkeypatch.setenv("POSTGRES_HOST", "example.com")
    model = TestModel.model_validate({"dsn": "postgresql://localhost/other"})
    assert model.dsn.scheme == "postgresql"
    assert not model.dsn.username
    assert not model.dsn.password
    assert model.dsn.host == "example.com"
    assert model.dsn.port == 8999
    assert model.dsn.path == "/other"
    assert not model.dsn.query

    with pytest.raises(ValidationError):
        TestModel.model_validate(
            {"dsn": "postgresql+psycopg2://localhost/other"}
        )


def test_env_redis_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    class TestModel(BaseModel):
        dsn: EnvRedisDsn

    monkeypatch.delenv("REDIS_6379_TCP_PORT", raising=False)
    monkeypatch.delenv("REDIS_HOST", raising=False)
    model = TestModel.model_validate(
        {"dsn": "redis://user:password@example.com:7777/1"}
    )
    assert model.dsn.scheme == "redis"
    assert model.dsn.username == "user"
    assert model.dsn.password == "password"
    assert model.dsn.host == "example.com"
    assert model.dsn.port == 7777
    assert model.dsn.path == "/1"

    model = TestModel.model_validate({"dsn": "redis://localhost"})
    assert model.dsn.scheme == "redis"
    assert not model.dsn.username
    assert not model.dsn.password
    assert model.dsn.host == "localhost"
    assert model.dsn.port == 6379
    assert model.dsn.path == "/0"

    monkeypatch.setenv("REDIS_6379_TCP_PORT", "4567")
    model = TestModel.model_validate(
        {"dsn": "redis://user:password@example.com:7777/1"}
    )
    assert model.dsn.scheme == "redis"
    assert model.dsn.username == "user"
    assert model.dsn.password == "password"
    assert model.dsn.host == "example.com"
    assert model.dsn.port == 4567
    assert model.dsn.path == "/1"

    monkeypatch.setenv("REDIS_HOST", "127.12.0.1")
    model = TestModel.model_validate({"dsn": "redis://localhost"})
    assert model.dsn.scheme == "redis"
    assert not model.dsn.username
    assert not model.dsn.password
    assert model.dsn.host == "127.12.0.1"
    assert model.dsn.port == 4567
    assert model.dsn.path == "/0"

    with pytest.raises(ValidationError):
        TestModel.model_validate({"dsn": "rediss://example.com/0"})


def test_human_timedelta() -> None:
    class TestModel(BaseModel):
        delta: HumanTimedelta

    model = TestModel.model_validate({"delta": timedelta(seconds=5)})
    assert model.delta == timedelta(seconds=5)
    assert model.model_dump(mode="python") == {"delta": timedelta(seconds=5)}
    assert model.model_dump(mode="json") == {"delta": 5}
    model = TestModel.model_validate({"delta": "4h5m18s"})
    assert model.delta == timedelta(hours=4, minutes=5, seconds=18)
    model = TestModel.model_validate({"delta": 600})
    assert model.delta == timedelta(seconds=600)
    assert model.model_dump(mode="python") == {"delta": timedelta(seconds=600)}
    model = TestModel.model_validate({"delta": 4.5})
    assert model.delta.total_seconds() == 4.5
    assert model.model_dump(mode="json") == {"delta": 4.5}
    model = TestModel.model_validate({"delta": "300"})
    assert model.delta == timedelta(seconds=300)
    model = TestModel.model_validate({"delta": "10.5"})
    assert model.delta.total_seconds() == 10.5

    with pytest.raises(ValidationError):
        TestModel.model_validate({"delta": "P1DT12H"})


def test_seconds_timedelta() -> None:
    class TestModel(BaseModel):
        delta: SecondsTimedelta

    model = TestModel.model_validate({"delta": timedelta(seconds=5)})
    assert model.delta == timedelta(seconds=5)
    assert model.model_dump(mode="python") == {"delta": timedelta(seconds=5)}
    assert model.model_dump(mode="json") == {"delta": 5}
    model = TestModel.model_validate({"delta": 600})
    assert model.delta == timedelta(seconds=600)
    assert model.model_dump(mode="python") == {"delta": timedelta(seconds=600)}
    model = TestModel.model_validate({"delta": 4.5})
    assert model.delta.total_seconds() == 4.5
    assert model.model_dump(mode="json") == {"delta": 4.5}
    model = TestModel.model_validate({"delta": "300"})
    assert model.delta == timedelta(seconds=300)
    model = TestModel.model_validate({"delta": "10.5"})
    assert model.delta.total_seconds() == 10.5

    with pytest.raises(ValidationError):
        TestModel.model_validate({"delta": "P1DT12H"})


@pytest.mark.filterwarnings("ignore:.*datetime.utcnow.*:DeprecationWarning")
def test_utcdatetime() -> None:
    class TestModel(BaseModel):
        time: UtcDatetime

    date = datetime.fromtimestamp(1668814932, tz=UTC)
    model = TestModel.model_validate({"time": 1668814932})
    assert model.time == date
    assert model.model_dump(mode="python") == {"time": date}
    round_trip = datetime.fromisoformat(model.model_dump(mode="json")["time"])
    assert round_trip == date

    mst_zone = timezone(-timedelta(hours=7))
    mst_date = datetime.now(tz=mst_zone)
    utc_date = mst_date.astimezone(UTC)
    assert TestModel.model_validate({"time": mst_date}).time == utc_date

    naive_date = datetime.utcnow()  # noqa: DTZ003
    aware_date = TestModel.model_validate({"time": naive_date}).time
    assert aware_date == naive_date.replace(tzinfo=UTC)
    assert aware_date.tzinfo == UTC

    model = TestModel.model_validate({"time": "2023-01-25T15:44:00+00:00"})
    assert model.time == datetime.fromisoformat("2023-01-25T15:44:00+00:00")
    assert model.time.tzinfo == UTC


def test_ivoaisodatetime() -> None:
    class TestModel(BaseModel):
        time: IvoaIsoDatetime

    date = datetime.fromisoformat("2023-01-25T15:44:34+00:00")
    model = TestModel.model_validate({"time": "2023-01-25T15:44:34Z"})
    assert model.time == date
    assert model.model_dump(mode="python") == {"time": date}
    assert model.model_dump(mode="json") == {"time": "2023-01-25T15:44:34Z"}
    model = TestModel.model_validate({"time": "2023-01-25T15:44:34"})
    assert model.time == date

    date = datetime.fromisoformat("2023-01-25").replace(tzinfo=UTC)
    assert TestModel.model_validate({"time": "2023-01-25"}).time == date

    with pytest.raises(ValidationError, match="does not match IVOA format"):
        TestModel.model_validate({"time": "2023-01-25T15:44:00+00:00"})

    with pytest.raises(ValidationError, match="Must be a string in"):
        TestModel.model_validate({"time": 1668814932})

    with pytest.raises(ValidationError, match="does not match IVOA format"):
        TestModel.model_validate({"time": "next thursday"})


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

    naive_date = datetime.utcnow()  # noqa: DTZ003
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
