"""Manage an async database session."""

from collections.abc import AsyncIterator

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

    async def __call__(self) -> AsyncIterator[async_scoped_session]:
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
        isolation_level: str | None = None,
    ) -> None:
        """Initialize the session dependency.

        Parameters
        ----------
        url
            Database connection URL, not including the password.
        password
            Database connection password.
        isolation_level
            If specified, sets a non-default isolation level for the database
            engine.
        """
        if self._engine:
            await self._engine.dispose()
        self._engine = create_database_engine(
            url, password, isolation_level=isolation_level
        )
        self._session = await create_async_session(self._engine)


db_session_dependency = DatabaseSessionDependency()
"""The dependency that will return the async session proxy."""
