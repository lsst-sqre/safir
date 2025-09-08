"""Manage an async database session."""

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import SecretStr
from pydantic_core import Url
from sqlalchemy.ext.asyncio import AsyncEngine, async_scoped_session

from safir.database import create_async_session, create_database_engine

__all__ = ["DatabaseSessionDependency", "db_session_dependency"]


class DatabaseSessionDependency:
    """Manages an async per-request SQLAlchemy session.

    Notes
    -----
    Creation of the database session factory has to be deferred until the
    configuration has been loaded, which in turn is deferred until app
    startup.

    In the app startup hook, run:

    .. code-block:: python

       await db_session_dependency.initialize(database_url)

    In the app shutdown hook, run:

    .. code-block:: python

       await db_session_dependency.aclose()

    An isolation level may optionally be configured when calling `initialize`.
    By default, a transaction is opened for every request and committed at the
    end of that request.  This can be configured when calling `initialize`.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session: async_scoped_session | None = None

    async def __call__(self) -> AsyncGenerator[async_scoped_session]:
        """Return the database session manager.

        Returns
        -------
        sqlalchemy.ext.asyncio.AsyncSession
            The newly-created session.
        """
        if not self._session:
            raise RuntimeError("db_session_dependency not initialized")
        try:
            yield self._session
        finally:
            # Following the recommendations in the SQLAlchemy documentation,
            # each session is scoped to a single web request. However, this
            # all uses the same async_scoped_session object, so should share
            # an underlying engine and connection pool.
            await self._session.remove()

    async def aclose(self) -> None:
        """Shut down the database engine."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None

    async def initialize(
        self,
        url: str | Url,
        password: str | SecretStr | None,
        *,
        connect_args: dict[str, Any] | None = None,
        isolation_level: str | None = None,
        max_overflow: int | None = None,
        pool_size: int | None = None,
        pool_timeout: float | None = None,
    ) -> None:
        """Initialize the session dependency.

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
            Maximum number of connections over the pool size for surge
            traffic.
        pool_size
            Connection pool size.
        pool_timeout
            How long to wait for a connection from the connection pool before
            giving up.
        """
        if self._engine:
            await self._engine.dispose()
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
        self._engine = create_database_engine(url, password, **kwargs)
        self._session = await create_async_session(self._engine)


db_session_dependency = DatabaseSessionDependency()
"""The dependency that will return the async session proxy."""
