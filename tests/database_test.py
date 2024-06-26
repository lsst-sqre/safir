"""Tests for the database utility functions."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import unquote, urlparse

import pytest
import structlog
from pydantic import BaseModel, SecretStr
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.future import select
from sqlalchemy.orm import declarative_base

from safir.database import (
    _build_database_url,
    create_async_session,
    create_database_engine,
    datetime_from_db,
    datetime_to_db,
    initialize_database,
)

TEST_DATABASE_PASSWORD = os.environ["TEST_DATABASE_PASSWORD"]

Base = declarative_base()


class User(Base):
    """Tiny database table for testing."""

    __tablename__ = "user"

    username: str = Column(String(64), primary_key=True)


@pytest.mark.asyncio
async def test_database_init(database_url: str) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, TEST_DATABASE_PASSWORD)
    await initialize_database(engine, logger, schema=Base.metadata, reset=True)
    session = await create_async_session(engine, logger)
    async with session.begin():
        session.add(User(username="someuser"))
    await session.remove()

    # Reinitializing the database without reset should preserve the row.
    await initialize_database(engine, logger, schema=Base.metadata)
    session = await create_async_session(engine, logger)
    async with session.begin():
        result = await session.scalars(select(User.username))
        assert result.all() == ["someuser"]
    await session.remove()

    # Reinitializing the database with reset should delete the data. Try
    # passing in the password as a SecretStr.
    password = SecretStr(TEST_DATABASE_PASSWORD)
    engine = create_database_engine(database_url, password)
    await initialize_database(engine, logger, schema=Base.metadata, reset=True)
    session = await create_async_session(engine, logger)
    async with session.begin():
        result = await session.scalars(select(User.username))
        assert result.all() == []
    await session.remove()
    await engine.dispose()


def test_build_database_url(database_url: str) -> None:
    url = _build_database_url("postgresql://foo@127.0.0.1/foo", None)
    assert url == "postgresql+asyncpg://foo@127.0.0.1/foo"

    url = _build_database_url("postgresql://foo@127.0.0.1:5432/foo", None)
    assert url == "postgresql+asyncpg://foo@127.0.0.1:5432/foo"

    url = _build_database_url("postgresql://foo@127.0.0.1/foo", "otherpass")
    assert url == "postgresql+asyncpg://foo:otherpass@127.0.0.1/foo"

    url = _build_database_url(
        "postgresql://foo@127.0.0.1:5433/foo", "otherpass"
    )
    assert url == "postgresql+asyncpg://foo:otherpass@127.0.0.1:5433/foo"

    # Test that the username and password are quoted properly.
    url = _build_database_url(
        "postgresql://foo%40e.com@127.0.0.1:4444/foo",
        "pass@word/with stuff",
    )
    assert url == (
        "postgresql+asyncpg://foo%40e.com:pass%40word%2Fwith%20stuff"
        "@127.0.0.1:4444/foo"
    )
    parsed_url = urlparse(url)
    assert parsed_url.username
    assert parsed_url.password

    # urlparse does not undo quoting in the components of netloc.
    assert unquote(parsed_url.username) == "foo@e.com"
    assert unquote(parsed_url.password) == "pass@word/with stuff"
    assert parsed_url.hostname == "127.0.0.1"
    assert parsed_url.port == 4444


@pytest.mark.asyncio
async def test_create_async_session(database_url: str) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, TEST_DATABASE_PASSWORD)
    await initialize_database(engine, logger, schema=Base.metadata, reset=True)

    session = await create_async_session(
        engine, logger, statement=select(User)
    )
    async with session.begin():
        session.add(User(username="foo"))
    await session.remove()

    # Use a query against a non-existent table as the liveness check and
    # ensure that fails.
    metadata = MetaData()
    bad_table = Table("bad", metadata, Column("name", String(64)))
    with pytest.raises(ProgrammingError):
        session = await create_async_session(
            engine, logger, statement=select(bad_table)
        )
    await engine.dispose()


def test_datetime() -> None:
    tz_aware = datetime.now(tz=UTC)
    tz_naive = tz_aware.replace(tzinfo=None)

    assert datetime_to_db(tz_aware) == tz_naive
    assert datetime_from_db(tz_naive) == tz_aware
    assert datetime_from_db(tz_aware) == tz_aware

    assert datetime_to_db(None) is None
    assert datetime_from_db(None) is None

    with pytest.raises(ValueError, match=r"datetime .* not in UTC"):
        datetime_to_db(tz_naive)

    tz_local = datetime.now(tz=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError, match=r"datetime .* not in UTC"):
        datetime_to_db(tz_local)
    with pytest.raises(ValueError, match=r"datetime .* not in UTC"):
        datetime_from_db(tz_local)

    # Pydantic's JSON decoder uses a TzInfo data structure instead of
    # datetime.timezone.utc. Make sure that's still recognized as UTC.
    class Test(BaseModel):
        time: datetime

    json_model = Test(time=tz_aware).model_dump_json()
    model = Test.model_validate_json(json_model)
    assert datetime_to_db(model.time) == tz_naive
