"""Tests for the database session dependency."""

from __future__ import annotations

from typing import Annotated

import pytest
import structlog
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from safir.database import (
    create_async_session,
    create_database_engine,
    initialize_database,
)
from safir.dependencies.db_session import db_session_dependency


class Base(DeclarativeBase):
    """Declarative base for testing."""


class User(Base):
    """Tiny database table for testing."""

    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(64), primary_key=True)


@pytest.mark.asyncio
async def test_session(database_url: str, database_password: str) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(database_url, database_password)
    await initialize_database(engine, logger, schema=Base.metadata, reset=True)
    session = await create_async_session(engine, logger)
    await db_session_dependency.initialize(database_url, database_password)

    app = FastAPI()

    @app.post("/add")
    async def add(
        session: Annotated[
            async_scoped_session, Depends(db_session_dependency)
        ],
    ) -> None:
        async with session.begin():
            session.add(User(username="foo"))

    @app.get("/list")
    async def get_list(
        session: Annotated[
            async_scoped_session, Depends(db_session_dependency)
        ],
    ) -> list[str]:
        async with session.begin():
            result = await session.scalars(select(User.username))
            return list(result.all())

    transport = ASGITransport(app=app)
    base_url = "https://example.com"
    async with AsyncClient(transport=transport, base_url=base_url) as client:
        r = await client.get("/list")
        assert r.status_code == 200
        assert r.json() == []

        r = await client.post("/add")
        assert r.status_code == 200

        r = await client.get("/list")
        assert r.status_code == 200
        assert r.json() == ["foo"]

    # Retrieve the database contents through an entirely separate connection
    # pool to check the transaction was really committed.
    async with session.begin():
        result = await session.scalars(select(User.username))
        assert result.all() == ["foo"]

    await session.remove()
    await engine.dispose()
    await db_session_dependency.aclose()
