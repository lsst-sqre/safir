"""Manage an async database session."""

from typing import TYPE_CHECKING, AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, async_scoped_session

from ..database import create_async_session, create_database_engine

# _IsolationLevel is defined in the SQLAlchemy type stubs as a long list of
# Literal options, which is not type-compatible with str.  Use this hack to
# use the correct list for type checking, but not for regular execution when
# the type stubs will not be loaded.
if TYPE_CHECKING:
    from sqlalchemy.engine.create import _IsolationLevel
else:
    _IsolationLevel = str

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
        self._engine: Optional[AsyncEngine] = None
        self._override_engine: Optional[AsyncEngine] = None
        self._session: Optional[async_scoped_session] = None

    async def __call__(self) -> AsyncIterator[async_scoped_session]:
        """Return the database session manager.

        Returns
        -------
        session : `sqlalchemy.ext.asyncio.AsyncSession`
            The newly-created session.
        """
        assert self._session, "db_session_dependency not initialized"
        yield self._session

        # Following the recommendations in the SQLAlchemy documentation, each
        # session is scoped to a single web request.  However, this all uses
        # the same async_scoped_session object, so should share an underlying
        # engine and connection pool.
        await self._session.remove()

    async def aclose(self) -> None:
        """Shut down the database engine."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None

    async def initialize(
        self,
        url: str,
        password: Optional[str],
        *,
        isolation_level: Optional[_IsolationLevel] = None,
    ) -> None:
        """Initialize the session dependency.

        Parameters
        ----------
        url : `str`
            Database connection URL, not including the password.
        password : `str` or `None`
            Database connection password.
        isolation_level : `str`, optional
            If specified, sets a non-default isolation level for the database
            engine.
        """
        if self._override_engine:
            self._session = await create_async_session(self._override_engine)
        else:
            self._engine = create_database_engine(
                url, password, isolation_level=isolation_level
            )
            self._session = await create_async_session(self._engine)

    def override_engine(self, engine: AsyncEngine) -> None:
        """Force the dependency to use the provided engine.

        Intended for testing, this allows the test suite to configure a single
        database engine and share it across all of the tests, benefiting from
        connection pooling for a minor test speed-up.  (This is not
        significant enough to bother with except for an extensive test suite.)

        Parameters
        ----------
        engine : `sqlalchemy.ext.asyncio.AsyncEngine`
            Database engine to use for all sessions.
        """
        self._override_engine = engine


db_session_dependency = DatabaseSessionDependency()
"""The dependency that will return the async session proxy."""
