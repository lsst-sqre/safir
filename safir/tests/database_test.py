"""Tests for the database utility functions."""

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import pytest
import structlog
from pydantic import BaseModel, SecretStr
from pydantic_core import Url
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.future import select

from safir.database import (
    create_async_session,
    create_database_engine,
    datetime_from_db,
    datetime_to_db,
    initialize_database,
    is_database_current,
    retry_async_transaction,
    stamp_database,
    stamp_database_async,
    unstamp_database,
)
from safir.database._connection import build_database_url

from .support.alembic import BaseV1, BaseV2, UserV1, UserV2, config


@pytest.mark.asyncio
async def test_database_init(
    database_url: str, database_password: str
) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, database_password)
    await initialize_database(
        engine, logger, schema=BaseV2.metadata, reset=True
    )
    session = await create_async_session(engine, logger)
    async with session.begin():
        session.add(UserV2(username="someuser"))
    await session.remove()

    # Reinitializing the database without reset should preserve the row.
    await initialize_database(engine, logger, schema=BaseV2.metadata)
    session = await create_async_session(engine, logger)
    async with session.begin():
        result = await session.scalars(select(UserV2.username))
        assert result.all() == ["someuser"]
    await session.remove()

    # Reinitializing the database with reset should delete the data. Try
    # passing in the password as a SecretStr.
    password = SecretStr(database_password)
    engine = create_database_engine(database_url, password)
    await initialize_database(
        engine, logger, schema=BaseV2.metadata, reset=True
    )
    session = await create_async_session(engine, logger)
    async with session.begin():
        result = await session.scalars(select(UserV2.username))
        assert result.all() == []
    await session.remove()
    await engine.dispose()


def test_build_database_url(database_url: str) -> None:
    url = build_database_url("postgresql://foo@127.0.0.1/foo", None)
    assert url == "postgresql+asyncpg://foo@127.0.0.1/foo"

    url = build_database_url("postgresql://foo@127.0.0.1:5432/foo", None)
    assert url == "postgresql+asyncpg://foo@127.0.0.1:5432/foo"

    url = build_database_url("postgresql://foo@127.0.0.1/foo", "otherpass")
    assert url == "postgresql+asyncpg://foo:otherpass@127.0.0.1/foo"

    url = build_database_url(
        "postgresql://foo@127.0.0.1:5433/foo", "otherpass"
    )
    assert url == "postgresql+asyncpg://foo:otherpass@127.0.0.1:5433/foo"

    pydantic_url = Url.build(
        scheme="postgresql", username="user", host="localhost", path="foo"
    )
    url = build_database_url(pydantic_url, "password")
    assert url == "postgresql+asyncpg://user:password@localhost/foo"

    # Test that the username and password are quoted properly.
    url = build_database_url(
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
async def test_create_async_session(
    database_url: str, database_password: str
) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, database_password)
    await initialize_database(
        engine, logger, schema=BaseV2.metadata, reset=True
    )

    session = await create_async_session(
        engine, logger, statement=select(UserV2)
    )
    async with session.begin():
        session.add(UserV2(username="foo"))
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


@pytest.mark.asyncio
async def test_retry_async_transaction(
    database_url: str, database_password: str
) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, database_password)
    await initialize_database(
        engine, logger, schema=BaseV2.metadata, reset=True
    )
    session = await create_async_session(engine, logger)
    async with session.begin():
        session.add(UserV2(username="someuser"))
    tries = 0

    @retry_async_transaction
    async def insert(attempts: int) -> None:
        nonlocal tries
        tries += 1
        async with session.begin():
            if tries <= attempts:
                raise OperationalError(None, None, ValueError("foo"))
            session.add(UserV2(username="newuser"))

    await insert(2)

    tries = 0
    with pytest.raises(OperationalError):
        await insert(3)

    @retry_async_transaction(max_tries=1)
    async def insert_capped(attempts: int) -> None:
        nonlocal tries
        tries += 1
        async with session.begin():
            if tries <= attempts:
                raise OperationalError(None, None, ValueError("foo"))
            session.add(UserV2(username="newuser"))

    tries = 0
    with pytest.raises(OperationalError):
        await insert_capped(1)

    await session.remove()
    await engine.dispose()


def test_alembic(
    database_url: str,
    database_password: str,
    monkeypatch: pytest.MonkeyPatch,
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    config.database_url = Url(database_url)
    config.database_password = SecretStr(database_password)
    config_path = (
        Path(__file__).parent / "data" / "database" / "v1" / "alembic.ini"
    )
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, database_password)

    async def init(schema: MetaData) -> None:
        await initialize_database(engine, logger, schema=schema, reset=True)

    async def check(config_path: Path) -> bool:
        return await is_database_current(engine, logger, config_path)

    async def store(record: Any) -> None:
        session = await create_async_session(engine, logger)
        async with session.begin():
            session.add(record)
        await session.remove()

    async def list_v2() -> list[str]:
        session = await create_async_session(engine, logger)
        async with session.begin():
            result = await session.scalars(select(UserV2.username))
        await session.remove()
        return list(result.all())

    # Initialize the database with the V1 schema.
    event_loop.run_until_complete(init(BaseV1.metadata))

    # Before stamping, the database should show as not up to date.
    assert not event_loop.run_until_complete(check(config_path))

    # Stamp the database.
    stamp_database(config_path)

    # Check that the database is up to date.
    assert event_loop.run_until_complete(check(config_path))

    # Store a record in the database.
    event_loop.run_until_complete(store(UserV1(username="foo", name="Foo")))

    # Check that the database is not current with the V2 schema.
    config_path = config_path.parent.parent / "v2" / "alembic.ini"
    assert not event_loop.run_until_complete(check(config_path))

    # Upgrade the database to V2. It should now show as current with the V2
    # schema.
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        cwd=str(config_path.parent),
        env={
            **os.environ,
            "TEST_DATABASE_URL": database_url,
            "TEST_DATABASE_PASSWORD": database_password,
            "PYTHONPATH": str(Path(__file__).parent.parent),
        },
    )
    assert event_loop.run_until_complete(check(config_path))

    # The data should still be there.
    assert event_loop.run_until_complete(list_v2()) == ["foo"]

    # Unstamping the database should cause it to no longer be current, but we
    # should be able to them stamp it async and then it should be current
    # again.
    event_loop.run_until_complete(unstamp_database(engine))
    assert not event_loop.run_until_complete(check(config_path))
    event_loop.run_until_complete(stamp_database_async(engine, config_path))
    assert event_loop.run_until_complete(check(config_path))
