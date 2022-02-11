"""Tests for the database utility functions."""

from __future__ import annotations

import os

import pytest
import structlog
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.future import select
from sqlalchemy.orm import declarative_base

from safir.database import (
    _build_database_url,
    create_async_session,
    create_database_engine,
    create_sync_session,
    initialize_database,
)

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
TEST_DATABASE_PASSWORD = os.getenv("TEST_DATABASE_PASSWORD")

Base = declarative_base()


class User(Base):
    """Tiny database table for testing."""

    __tablename__ = "user"

    username: str = Column(String(64), primary_key=True)


@pytest.mark.asyncio
async def test_database_init() -> None:
    logger = structlog.get_logger(__name__)
    engine = await initialize_database(
        TEST_DATABASE_URL,
        TEST_DATABASE_PASSWORD,
        logger,
        schema=Base.metadata,
        reset=True,
    )
    session = await create_async_session(engine, logger)
    async with session.begin():
        session.add(User(username="someuser"))
    await session.remove()
    await engine.dispose()

    # Reinitializing the database without reset should preserve the row.
    engine = await initialize_database(
        TEST_DATABASE_URL,
        TEST_DATABASE_PASSWORD,
        logger,
        schema=Base.metadata,
    )
    session = await create_async_session(engine, logger)
    async with session.begin():
        result = await session.scalars(select(User.username))
        assert result.all() == ["someuser"]
    await session.remove()
    await engine.dispose()

    # Reinitializing the database with reset should delete the data.
    engine = await initialize_database(
        TEST_DATABASE_URL,
        TEST_DATABASE_PASSWORD,
        logger,
        schema=Base.metadata,
        reset=True,
    )
    session = await create_async_session(engine, logger)
    async with session.begin():
        result = await session.scalars(select(User.username))
        assert result.all() == []
    await session.remove()
    await engine.dispose()


def test_build_database_url() -> None:
    url = _build_database_url(TEST_DATABASE_URL, None, is_async=False)
    assert url == TEST_DATABASE_URL

    url = _build_database_url(
        "postgresql://foo@127.0.0.1/foo", "password", is_async=False
    )
    assert url == "postgresql://foo:password@127.0.0.1/foo"

    url = _build_database_url(
        "postgresql://foo@127.0.0.1/foo", None, is_async=True
    )
    assert url == "postgresql+asyncpg://foo@127.0.0.1/foo"

    url = _build_database_url(
        "postgresql://foo@127.0.0.1/foo", "otherpass", is_async=True
    )
    assert url == "postgresql+asyncpg://foo:otherpass@127.0.0.1/foo"


@pytest.mark.asyncio
async def test_create_async_session() -> None:
    logger = structlog.get_logger(__name__)
    engine = await initialize_database(
        TEST_DATABASE_URL,
        TEST_DATABASE_PASSWORD,
        logger,
        schema=Base.metadata,
        reset=True,
    )
    await engine.dispose()

    engine = create_database_engine(TEST_DATABASE_URL, TEST_DATABASE_PASSWORD)
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


@pytest.mark.asyncio
async def test_create_sync_session() -> None:
    logger = structlog.get_logger(__name__)
    engine = await initialize_database(
        TEST_DATABASE_URL,
        TEST_DATABASE_PASSWORD,
        logger,
        schema=Base.metadata,
        reset=True,
    )
    await engine.dispose()

    session = create_sync_session(
        TEST_DATABASE_URL,
        TEST_DATABASE_PASSWORD,
        logger,
        statement=select(User),
    )
    with session.begin():
        session.add(User(username="foo"))
    session.remove()

    # Use a query against a non-existent table as the liveness check and
    # ensure that fails.
    metadata = MetaData()
    bad_table = Table("bad", metadata, Column("name", String(64)))
    with pytest.raises(ProgrammingError):
        session = create_sync_session(
            TEST_DATABASE_URL,
            TEST_DATABASE_PASSWORD,
            logger,
            statement=select(bad_table),
        )
