"""Utility functions for database management."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional, overload
from urllib.parse import quote, urlparse

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.schema import CreateSchema
from sqlalchemy.sql.expression import Select
from sqlalchemy.sql.schema import MetaData
from structlog.stdlib import BoundLogger

__all__ = [
    "DatabaseInitializationError",
    "create_async_session",
    "create_database_engine",
    "create_sync_session",
    "datetime_from_db",
    "datetime_to_db",
    "initialize_database",
]


class DatabaseInitializationError(Exception):
    """Database initialization failed."""


def _build_database_url(
    url: str, password: str | None, *, is_async: bool
) -> str:
    """Build the authenticated URL for the database.

    Parameters
    ----------
    url
        Database connection URL, not including the password.
    password
        Database connection password.
    is_async
        Whether the resulting URL should be async or not.

    Returns
    -------
    url
        The URL including the password.

    Raises
    ------
    ValueError
        A password was provided but the connection URL has no username.
    """
    if is_async or password:
        parsed_url = urlparse(url)
        if is_async and parsed_url.scheme == "postgresql":
            parsed_url = parsed_url._replace(scheme="postgresql+asyncpg")
        if password:
            if not parsed_url.username:
                raise ValueError(f"No username in database URL {url}")
            password = quote(password, safe="")

            # The username portion of the parsed URL does not appear to decode
            # URL escaping of the username, so we should not quote it again or
            # we will get double-quoting.
            netloc = f"{parsed_url.username}:{password}@{parsed_url.hostname}"
            if parsed_url.port:
                netloc = f"{netloc}:{parsed_url.port}"
            parsed_url = parsed_url._replace(netloc=netloc)
        url = parsed_url.geturl()
    return url


@overload
def datetime_from_db(time: datetime) -> datetime:
    ...


@overload
def datetime_from_db(time: None) -> None:
    ...


def datetime_from_db(time: datetime | None) -> datetime | None:
    """Add the UTC time zone to a naive datetime from the database.

    Parameters
    ----------
    time
        The naive datetime from the database, or `None`.

    Returns
    -------
    datetime.datetime or None
        `None` if the input was none, otherwise a timezone-aware version of
        the same `~datetime.datetime` in the UTC timezone.
    """
    if not time:
        return None
    if time.tzinfo not in (None, timezone.utc):
        raise ValueError(f"datetime {time} not in UTC")
    return time.replace(tzinfo=timezone.utc)


@overload
def datetime_to_db(time: datetime) -> datetime:
    ...


@overload
def datetime_to_db(time: None) -> None:
    ...


def datetime_to_db(time: datetime | None) -> datetime | None:
    """Strip time zone for storing a datetime in the database.

    Parameters
    ----------
    time
        The timezone-aware `~datetime.datetime` in the UTC time zone, or
        `None`.

    Returns
    -------
    datetime.datetime or None
        `None` if the input was `None`, otherwise the same
        `~datetime.datetime` but timezone-naive and thus suitable for storing
        in a SQL database.
    """
    if not time:
        return None
    if time.tzinfo != timezone.utc:
        raise ValueError(f"datetime {time} not in UTC")
    return time.replace(tzinfo=None)


def create_database_engine(
    url: str,
    password: str | None,
    *,
    isolation_level: Optional[str] = None,
) -> AsyncEngine:
    """Create a new async database engine.

    Parameters
    ----------
    url
        Database connection URL, not including the password.
    password
        Database connection password.
    isolation_level
        If specified, sets a non-default isolation level for the database
        engine.

    Returns
    -------
    sqlalchemy.ext.asyncio.AsyncEngine
        Newly-created database engine.  When done with the engine, the caller
        must call ``await engine.dispose()``.

    Raises
    ------
    ValueError
        A password was provided but the connection URL has no username.
    """
    url = _build_database_url(url, password, is_async=True)
    if isolation_level:
        return create_async_engine(
            url, future=True, isolation_level=isolation_level
        )
    else:
        return create_async_engine(url, future=True)


async def create_async_session(
    engine: AsyncEngine,
    logger: Optional[BoundLogger] = None,
    *,
    statement: Optional[Select] = None,
) -> async_scoped_session:
    """Create a new async database session.

    Optionally checks that the database is available and retries in a loop for
    10s if it is not.  This should be used during application startup to wait
    for any network setup or database proxy sidecar.

    Parameters
    ----------
    engine
        Database engine to use for the session.
    logger
        Logger for reporting errors.  Used only if a statement is provided.
    statement
        If provided, statement to run to check database connectivity.  This
        will be modified with ``limit(1)`` before execution.  If not provided,
        database connectivity will not be checked.

    Returns
    -------
    sqlalchemy.ext.asyncio.async_scoped_session
        The database session proxy.  This is an asyncio scoped session that is
        scoped to the current task, which means that it will materialize new
        AsyncSession objects for each asyncio task (and thus each web
        request).  ``await session.remove()`` should be called when the caller
        is done with the session.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = async_scoped_session(factory, scopefunc=asyncio.current_task)

    # If no statement was provided, just return the async_scoped_session.
    if statement is None:
        return session

    # A statement was provided, so we want to check connectivity and retry for
    # up to ten seconds before returning the session.
    for _ in range(5):
        try:
            async with session.begin():
                await session.execute(statement.limit(1))
                return session
        except (ConnectionRefusedError, OperationalError, OSError):
            if logger:
                logger.info("database not ready, waiting two seconds")
            await session.remove()
            await asyncio.sleep(2)
            continue

    # If we got here, we failed five times.  Try one last time without
    # catching exceptions so that we raise the appropriate exception to our
    # caller.
    async with session.begin():
        await session.execute(statement.limit(1))
        return session


def create_sync_session(
    url: str,
    password: str | None,
    logger: Optional[BoundLogger] = None,
    *,
    isolation_level: Optional[str] = None,
    statement: Optional[Select] = None,
) -> scoped_session:
    """Create a new sync database session.

    Used instead of `create_database_engine` and `create_async_session` for
    sync code, such as Dramatiq workers.  This combines engine creation with
    session creation.

    Parameters
    ----------
    url
        Database connection URL, not including the password.
    password
        Database connection password.
    logger
        Logger for reporting errors.  Used only if a statement is provided.
    isolation_level
        If specified, sets a non-default isolation level for the database
        engine.
    statement
        If provided, statement to run to check database connectivity.  This
        will be modified with ``limit(1)`` before execution.  If not provided,
        database connectivity will not be checked.

    Returns
    -------
    sqlalchemy.orm.scoping.scoped_session
        The database session proxy.  This manages a separate session per
        thread and therefore should be thread-safe.

    Raises
    ------
    ValueError
        A password was provided but the connection URL has no username.
    """
    url = _build_database_url(url, password, is_async=False)
    if isolation_level:
        engine = create_engine(url, isolation_level=isolation_level)
    else:
        engine = create_engine(url)
    factory = sessionmaker(bind=engine, future=True)
    session = scoped_session(factory)

    # If no statement was provided, just return the scoped_session.
    if statement is None:
        return session

    # A statement was provided, so we want to check connectivity and retry for
    # up to ten seconds before returning the session.
    for _ in range(5):
        try:
            with session.begin():
                session.execute(statement.limit(1))
                return session
        except (ConnectionRefusedError, OperationalError, OSError):
            if logger:
                logger.info("database not ready, waiting two seconds")
            session.remove()
            time.sleep(2)
            continue

    # If we got here, we failed five times.  Try one last time without
    # catching exceptions so that we raise the appropriate exception to our
    # caller.
    with session.begin():
        session.execute(statement.limit(1))
        return session


async def initialize_database(
    engine: AsyncEngine,
    logger: BoundLogger,
    *,
    schema: MetaData,
    reset: bool = False,
) -> None:
    """Create and initialize a new database.

    Parameters
    ----------
    engine
        Database engine to use.  Create with `create_database_engine`.
    logger
        Logger used to report problems
    schema
        Metadata for the database schema.  Generally this will be
        ``Base.metadata`` where ``Base`` is the declarative base used as the
        base class for all ORM table definitions.  The caller must ensure that
        all table definitions have been imported by Python before calling this
        function, or parts of the schema will be missing.
    reset
        If set to `True`, drop all tables and reprovision the database.
        Useful when running tests with an external database.

    Raises
    ------
    DatabaseInitializationError
        After five attempts, the database still could not be initialized.
        This is normally due to some connectivity issue to the database.
    """
    success = False
    error = None
    for _ in range(5):
        try:
            async with engine.begin() as conn:
                if schema.schema is not None:
                    await conn.execute(CreateSchema(schema.schema, True))
                if reset:
                    await conn.run_sync(schema.drop_all)
                await conn.run_sync(schema.create_all)
            success = True
        except (ConnectionRefusedError, OperationalError, OSError) as e:
            logger.info("database not ready, waiting two seconds")
            error = str(e)
            await asyncio.sleep(2)
            continue
        if success:
            logger.info("initialized database schema")
            break
    if not success:
        msg = "database schema initialization failed (database not reachable?)"
        logger.error(msg)
        await engine.dispose()
        raise DatabaseInitializationError(error)
