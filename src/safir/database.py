"""Utility functions for database management."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    create_async_engine,
)
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.sql.expression import Select
from sqlalchemy.sql.schema import MetaData
from structlog.stdlib import BoundLogger

# _IsolationLevel is defined in the SQLAlchemy type stubs as a long list of
# Literal options, which is not type-compatible with str.  Use this hack to
# use the correct list for type checking, but not for regular execution when
# the type stubs will not be loaded.
if TYPE_CHECKING:
    from sqlalchemy.engine.create import _IsolationLevel
else:
    _IsolationLevel = str

__all__ = [
    "create_async_session",
    "create_database_engine",
    "create_sync_session",
    "initialize_database",
]


class DatabaseInitializationError(Exception):
    """Database initialization failed."""


def _build_database_url(
    url: str, password: Optional[str], *, is_async: bool
) -> str:
    """Build the authenticated URL for the database.

    Parameters
    ----------
    url : `str`
        Database connection URL, not including the password.
    password : `str` or `None`
        Database connection password.
    is_async : `bool`
        Whether the resulting URL should be async or not.

    Returns
    -------
    url : `str`
        The URL including the password.
    """
    if is_async or password:
        parsed_url = urlparse(url)
        if is_async and parsed_url.scheme == "postgresql":
            parsed_url = parsed_url._replace(scheme="postgresql+asyncpg")
        if password:
            netloc = f"{parsed_url.username}:{password}@{parsed_url.hostname}"
            parsed_url = parsed_url._replace(netloc=netloc)
        url = parsed_url.geturl()
    return url


def create_database_engine(
    url: str,
    password: Optional[str],
    *,
    isolation_level: Optional[_IsolationLevel] = None,
) -> AsyncEngine:
    """Create a new async database engine.

    Parameters
    ----------
    url : `str`
        Database connection URL, not including the password.
    password : `str` or `None`
        Database connection password.
    isolation_level : `str`, optional
        If specified, sets a non-default isolation level for the database
        engine.

    Returns
    -------
    engine : `sqlalchemy.ext.asyncio.AsyncEngine`
        Newly-created database engine.  When done with the engine, the caller
        must call ``await engine.dispose()``.
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
    engine : `sqlalchemy.ext.asyncio.AsyncEngine`
        Database engine to use for the session.
    logger : ``structlog.stdlib.BoundLogger``, optional
        Logger for reporting errors.  Used only if a statement is provided.
    statement : `sqlalchemy.sql.expression.Select`, optional
        If provided, statement to run to check database connectivity.  This
        will be modified with ``limit(1)`` before execution.  If not provided,
        database connectivity will not be checked.

    Returns
    -------
    session : `sqlalchemy.ext.asyncio.async_scoped_session`
        The database session proxy.  This is an asyncio scoped session that is
        scoped to the current task, which means that it will materialize new
        AsyncSession objects for each asyncio task (and thus each web
        request).  ``await session.remove()`` should be called when the caller
        is done with the session.
    """
    factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
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
        except (ConnectionRefusedError, OperationalError):
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
    password: Optional[str],
    logger: Optional[BoundLogger] = None,
    *,
    isolation_level: Optional[_IsolationLevel] = None,
    statement: Optional[Select] = None,
) -> scoped_session:
    """Create a new sync database session.

    Used instead of `create_database_engine` and `create_async_session` for
    sync code, such as Dramatiq workers.  This combines engine creation with
    session creation.

    Parameters
    ----------
    url : `str`
        Database connection URL, not including the password.
    password : `str` or `None`
        Database connection password.
    logger : ``structlog.stdlib.BoundLogger``, optional
        Logger for reporting errors.  Used only if a statement is provided.
    isolation_level : `str`, optional
        If specified, sets a non-default isolation level for the database
        engine.
    statement : `sqlalchemy.sql.expression.Select`, optional
        If provided, statement to run to check database connectivity.  This
        will be modified with ``limit(1)`` before execution.  If not provided,
        database connectivity will not be checked.

    Returns
    -------
    session : `sqlalchemy.orm.scoped_session`
        The database session proxy.  This manages a separate session per
        thread and therefore should be thread-safe.
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
        except OperationalError:
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
    url: str,
    password: Optional[str],
    logger: BoundLogger,
    *,
    schema: MetaData,
    reset: bool = False,
) -> AsyncEngine:
    """Create and initialize a new database.

    Parameters
    ----------
    url : `str`
        Database connection URL, not including the password.
    password : `str` or `None`
        Database connection password.
    logger : ``structlog.stdlib.BoundLogger``
        Logger used to report problems
    schema : `sqlalchemy.sql.schema.MetaData`
        Metadata for the database schema.  Generally this will be
        ``Base.metadata`` where ``Base`` is the declarative base used as the
        base class for all ORM table definitions.  The caller must ensure that
        all table definitions have been imported by Python before calling this
        function, or parts of the schema will be missing.
    reset : `bool`, optional
        If set to `True`, drop all tables and reprovision the database.
        Useful when running tests with an external database.  Default is
        `False`.

    Returns
    -------
    engine : `sqlalchemy.ext.asyncio.AsyncEngine`
        Database engine for the initialized database.  This may be used by the
        caller to perform any additional necessary database initialization not
        included in the schema, such as adding default table rows.  The engine
        must then be closed with ``await engine.dispose()``.

    Raises
    ------
    DatabaseInitializationError
        After five attempts, the database still could not be initialized.
        This is normally due to some connectivity issue to the database.
    """
    success = False
    error = None
    engine = create_database_engine(url, password)
    for _ in range(5):
        try:
            async with engine.begin() as conn:
                if reset:
                    await conn.run_sync(schema.drop_all)
                await conn.run_sync(schema.create_all)
            success = True
        except (ConnectionRefusedError, OperationalError) as e:
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
    return engine
