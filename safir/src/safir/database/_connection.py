"""Managing database engines and sessions."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote, urlparse

from pydantic import SecretStr
from pydantic_core import Url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql.expression import Select
from structlog.stdlib import BoundLogger

__all__ = [
    "build_database_url",
    "create_async_session",
    "create_database_engine",
]


def build_database_url(
    url: str | Url, password: str | SecretStr | None, *, is_async: bool = True
) -> str:
    """Build the authenticated URL for the database.

    Unless ``is_async`` is set to `False`, the database scheme is forced to
    ``postgresql+asyncpg`` if it is ``postgresql``, and ``mysql+asyncmy`` if
    it is ``mysql``.

    Parameters
    ----------
    url
        Database connection URL, not including the password.
    password
        Database connection password.
    is_async
        Whether to force an async driver.

    Returns
    -------
    url
        URL including the password.

    Raises
    ------
    ValueError
        Raised if a password was provided but the connection URL has no
        username.
    """
    if not isinstance(url, str):
        url = str(url)
    parsed_url = urlparse(url)
    if parsed_url.scheme == "postgresql":
        parsed_url = parsed_url._replace(scheme="postgresql+asyncpg")
    elif parsed_url.scheme == "mysql":
        parsed_url = parsed_url._replace(scheme="mysql+asyncmy")
    if password:
        if isinstance(password, SecretStr):
            password = password.get_secret_value()
        if not parsed_url.username:
            raise ValueError(f"No username in database URL {url}")
        password = quote(password, safe="")

        # The username portion of the parsed URL does not appear to decode URL
        # escaping of the username, so we should not quote it again or we will
        # get double-quoting.
        netloc = f"{parsed_url.username}:{password}@{parsed_url.hostname}"
        if parsed_url.port:
            netloc = f"{netloc}:{parsed_url.port}"
        parsed_url = parsed_url._replace(netloc=netloc)
    return parsed_url.geturl()


def create_database_engine(
    url: str | Url,
    password: str | SecretStr | None,
    *,
    connect_args: dict[str, Any] | None = None,
    isolation_level: str | None = None,
    max_overflow: int | None = None,
    pool_size: int | None = None,
    pool_timeout: float | None = None,
) -> AsyncEngine:
    """Create a new async database engine.

    Parameters
    ----------
    url
        Database connection URL, not including the password.
    password
        Database connection password.
    connect_args
        Additional connection arguments to pass directly to the underlying
        database driver.
    isolation_level
        If specified, sets a non-default isolation level for the database
        engine.
    max_overflow
        Maximum number of connections over the pool size for surge traffic.
    pool_size
        Connection pool size.
    pool_timeout
        How long to wait for a connection from the connection pool before
        giving up.

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
    url = build_database_url(url, password)
    kwargs: dict[str, Any] = {}
    if connect_args:
        kwargs["connect_args"] = connect_args
    if isolation_level:
        kwargs["isolation_level"] = isolation_level
    if max_overflow is not None:
        kwargs["max_overflow"] = max_overflow
    if pool_size is not None:
        kwargs["pool_size"] = pool_size
    if pool_timeout is not None:
        kwargs["pool_timeout"] = pool_timeout
    return create_async_engine(url, **kwargs)


async def create_async_session(
    engine: AsyncEngine,
    logger: BoundLogger | None = None,
    *,
    statement: Select | None = None,
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
