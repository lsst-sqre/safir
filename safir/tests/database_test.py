"""Tests for the database utility functions."""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Self
from urllib.parse import unquote, urlparse

import pytest
import structlog
from pydantic import BaseModel, SecretStr
from pydantic_core import Url
from sqlalchemy import Column, MetaData, Select, String, Table, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import (
    DeclarativeBase,
    InstrumentedAttribute,
    Mapped,
    mapped_column,
)
from starlette.datastructures import URL

from safir.database import (
    DatetimeIdCursor,
    PaginatedQueryRunner,
    PaginationLinkData,
    create_async_session,
    create_database_engine,
    datetime_from_db,
    datetime_to_db,
    drop_database,
    initialize_database,
    is_database_current,
    retry_async_transaction,
    stamp_database,
    stamp_database_async,
    unstamp_database,
)
from safir.database._connection import build_database_url
from safir.pydantic import UtcDatetime

from .support.alembic import BaseV1, BaseV2, UserV1, UserV2, config


@pytest.mark.asyncio
async def test_initialize_database(
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


@pytest.mark.asyncio
async def test_drop_database(
    database_url: str, database_password: str
) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, database_password)
    await initialize_database(engine, logger, schema=BaseV2.metadata)
    session = await create_async_session(engine, logger)
    async with session.begin():
        session.add(UserV2(username="someuser"))
    await session.remove()

    await drop_database(engine, BaseV2.metadata)
    session = await create_async_session(engine, logger)
    with pytest.raises(ProgrammingError):
        async with session.begin():
            await session.scalars(select(UserV2.username))
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


class PaginationBase(DeclarativeBase):
    pass


class PaginationTable(PaginationBase):
    __tablename__ = "table"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    time: Mapped[datetime]

    def __repr__(self) -> str:
        return f"PaginationTable(id={self.id}, time={self.time})"


class PaginationModel(BaseModel):
    id: int
    time: UtcDatetime


@dataclass
class TableCursor(DatetimeIdCursor[PaginationModel]):
    @staticmethod
    def id_column() -> InstrumentedAttribute:
        return PaginationTable.id

    @staticmethod
    def time_column() -> InstrumentedAttribute:
        return PaginationTable.time

    @classmethod
    def from_entry(
        cls, entry: PaginationModel, *, reverse: bool = False
    ) -> Self:
        return cls(time=entry.time, id=entry.id, previous=reverse)


def naive_datetime(timestamp: float) -> datetime:
    """Construct timezone-naive datetimes for tests."""
    return datetime_to_db(datetime.fromtimestamp(timestamp, tz=UTC))


def assert_model_lists_equal(
    a: list[PaginationModel], b: list[PaginationTable]
) -> None:
    assert len(a) == len(b)
    for index, entry in enumerate(a):
        assert entry.id == b[index].id, f"element {index} id"
        orm_time = b[index].time.replace(tzinfo=UTC)
        assert entry.time == orm_time, f"element {index} time"


@pytest.mark.asyncio
async def test_pagination(database_url: str, database_password: str) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, database_password)
    await initialize_database(
        engine, logger, schema=PaginationBase.metadata, reset=True
    )
    session = await create_async_session(engine, logger)

    # Add the test database rows in a random order so that the ordering of
    # unique IDs does not match the ordering of the timestamps.
    rows = [
        PaginationTable(time=naive_datetime(1600000000.5)),
        PaginationTable(time=naive_datetime(1510000000)),
        PaginationTable(time=naive_datetime(1520000000)),
        PaginationTable(time=naive_datetime(1500000000)),
        PaginationTable(time=naive_datetime(1520000000)),
        PaginationTable(time=naive_datetime(1600000000.5)),
        PaginationTable(time=naive_datetime(1610000000)),
    ]
    async with session.begin():
        for row in rows:
            session.add(row)

    # Rows will be returned from the database in reverse order, so change the
    # rows data structure to match.
    rows.sort(key=lambda e: (e.time, e.id), reverse=True)

    # Query by object and test the pagination cursors going backwards and
    # forwards.
    builder = PaginatedQueryRunner(PaginationModel, TableCursor)
    async with session.begin():
        stmt: Select[tuple] = select(PaginationTable)
        assert await builder.query_count(session, stmt) == 7
        result = await builder.query_object(session, stmt, limit=2)
        assert_model_lists_equal(result.entries, rows[:2])
        assert not result.prev_cursor
        base_url = URL("https://example.com/query")
        next_url = f"{base_url!s}?cursor={result.next_cursor}"
        assert result.link_header(base_url) == (
            f'<{base_url!s}>; rel="first", ' f'<{next_url}>; rel="next"'
        )
        assert result.first_url(base_url) == str(base_url)
        assert result.next_url(base_url) == next_url
        assert result.prev_url(base_url) is None
        assert str(result.next_cursor) == "1600000000.5_1"

        result = await builder.query_object(
            session, stmt, cursor=result.next_cursor, limit=3
        )
        assert_model_lists_equal(result.entries, rows[2:5])
        assert str(result.next_cursor) == "1510000000_2"
        assert str(result.prev_cursor) == "p1600000000.5_1"
        base_url = URL("https://example.com/query?foo=bar&foo=baz&cursor=xxxx")
        stripped_url = "https://example.com/query?foo=bar&foo=baz"
        next_url = f"{stripped_url}&cursor={result.next_cursor}"
        prev_url = f"{stripped_url}&cursor={result.prev_cursor}"
        assert result.link_header(base_url) == (
            f'<{stripped_url}>; rel="first", '
            f'<{next_url}>; rel="next", '
            f'<{prev_url}>; rel="prev"'
        )
        assert result.first_url(base_url) == stripped_url
        assert result.next_url(base_url) == next_url
        assert result.prev_url(base_url) == prev_url
        next_cursor = result.next_cursor

        result = await builder.query_object(
            session, stmt, cursor=result.prev_cursor
        )
        assert_model_lists_equal(result.entries, rows[:2])
        base_url = URL("https://example.com/query?limit=2")
        assert result.link_header(base_url) == (
            f'<{base_url!s}>; rel="first", '
            f'<{base_url!s}&cursor={result.next_cursor}>; rel="next"'
        )

        result = await builder.query_object(session, stmt, cursor=next_cursor)
        assert_model_lists_equal(result.entries, rows[5:])
        assert not result.next_cursor
        base_url = URL("https://example.com/query")
        assert result.next_url(base_url) is None
        assert result.link_header(base_url) == (
            f'<{base_url!s}>; rel="first", '
            f'<{base_url!s}?cursor={result.prev_cursor}>; rel="prev"'
        )
        prev_cursor = result.prev_cursor

        result = await builder.query_object(session, stmt, cursor=prev_cursor)
        assert_model_lists_equal(result.entries, rows[:5])
        assert result.link_header(base_url) == (
            f'<{base_url!s}>; rel="first", '
            f'<{base_url!s}?cursor={result.next_cursor}>; rel="next"'
        )

        result = await builder.query_object(
            session, stmt, cursor=prev_cursor, limit=2
        )
        assert_model_lists_equal(result.entries, rows[3:5])
        assert str(result.prev_cursor) == "p1520000000_5"
        assert result.link_header(base_url) == (
            f'<{base_url!s}>; rel="first", '
            f'<{base_url!s}?cursor={result.next_cursor}>; rel="next", '
            f'<{base_url!s}?cursor={result.prev_cursor}>; rel="prev"'
        )

    # Perform one of the queries by attribute instead to test the query_row
    # function.
    async with session.begin():
        stmt = select(PaginationTable.time, PaginationTable.id)
        result = await builder.query_row(session, stmt, limit=2)
        assert_model_lists_equal(result.entries, rows[:2])
        assert await builder.query_count(session, stmt) == 7

    # Querying for the entire table should return the everything with no
    # pagination cursors. Try this with both an object query and an attribute
    # query.
    async with session.begin():
        result = await builder.query_object(session, select(PaginationTable))
        assert_model_lists_equal(result.entries, rows)
        assert not result.next_cursor
        assert not result.prev_cursor
        stmt = select(PaginationTable.id, PaginationTable.time)
        result = await builder.query_row(session, stmt)
        assert_model_lists_equal(result.entries, rows)
        assert not result.next_cursor
        assert not result.prev_cursor
        base_url = URL("https://example.com/query?foo=b")
        assert result.link_header(base_url) == (f'<{base_url!s}>; rel="first"')


def test_link_data() -> None:
    header = (
        '<https://example.com/query>; rel="first", '
        '<https://example.com/query?cursor=1600000000.5_1>; rel="next"'
    )
    link = PaginationLinkData.from_header(header)
    assert not link.prev_url
    assert link.next_url == "https://example.com/query?cursor=1600000000.5_1"
    assert link.first_url == "https://example.com/query"

    header = (
        '<https://example.com/query?limit=10>; rel="first", '
        '<https://example.com/query?limit=10&cursor=15_2>; rel="next", '
        '<https://example.com/query?limit=10&cursor=p5_1>; rel="prev"'
    )
    link = PaginationLinkData.from_header(header)
    assert link.prev_url == "https://example.com/query?limit=10&cursor=p5_1"
    assert link.next_url == "https://example.com/query?limit=10&cursor=15_2"
    assert link.first_url == "https://example.com/query?limit=10"

    header = (
        '<https://example.com/query>; rel="first", '
        '<https://example.com/query?cursor=p1510000000_2>; rel="previous"'
    )
    link = PaginationLinkData.from_header(header)
    assert link.prev_url == "https://example.com/query?cursor=p1510000000_2"
    assert not link.next_url
    assert link.first_url == "https://example.com/query"

    header = '<https://example.com/query?foo=b>; rel="first"'
    link = PaginationLinkData.from_header(header)
    assert not link.prev_url
    assert not link.next_url
    assert link.first_url == "https://example.com/query?foo=b"

    link = PaginationLinkData.from_header("")
    assert not link.prev_url
    assert not link.next_url
    assert not link.first_url
