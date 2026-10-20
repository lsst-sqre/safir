"""Database engine management."""

from abc import ABCMeta, abstractmethod
from types import TracebackType
from typing import Any, Literal, override

try:
    from google.cloud.sql.connector import (
        Connector,
        IPTypes,
        create_async_connector,
    )
    from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
except ImportError as e:
    raise ImportError(
        "The safir.database module requires the db extra. "
        "Install it with `pip install safir[db]`."
    ) from e

from ._config import CloudSqlSettings, DatabaseSettings

__all__ = [
    "CloudSqlEngineManager",
    "DatabaseEngineManager",
    "EngineManager",
    "engine_manager",
]


class EngineManager(metaclass=ABCMeta):
    """Base class for database engine management.

    This class should be created via `engine_manager`, not directly.

    Parameters
    ----------
    connect_args
        Additional connection arguments to pass directly to the underlying
        database driver.
    """

    def __init__(self, connect_args: dict[str, Any] | None) -> None:
        self._connect_args = connect_args
        self._engine: AsyncEngine | None = None

    async def __aenter__(self) -> AsyncEngine:
        return await self.create_engine()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        await self.aclose()
        return False

    async def aclose(self) -> None:
        """Close the engine and all associated resources."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None

    @abstractmethod
    async def create_engine(self) -> AsyncEngine:
        """Create a new database engine.

        Prefer using this class as a context manager instead where possible.
        If this method is used, the caller must call `aclose` on this object
        when the engine is no longer needed rather than calling the
        `~AsyncEngine.dispose` method directly.

        Returns
        -------
        AsyncEngine
            Newly-created database engine.
        """


class CloudSqlEngineManager(EngineManager):
    """Manages a Cloud SQL database engine and its associated resources.

    This class should be created via `engine_manager`, not directly.

    Parameters
    ----------
    config
        Connection configuration for the Cloud SQL database.
    connect_args
        Additional connection arguments to pass directly to the underlying
        database driver.
    """

    def __init__(
        self, config: CloudSqlSettings, connect_args: dict[str, Any] | None
    ) -> None:
        super().__init__(connect_args)
        self._config = config
        self._connector: Connector | None = None

    @override
    async def aclose(self) -> None:
        if self._connector:
            await self._connector.close_async()
            self._connector = None
        await super().aclose()

    @override
    async def create_engine(self) -> AsyncEngine:
        if self._engine:
            raise RuntimeError("Call aclose before creating another engine")
        connector = await create_async_connector(enable_iam_auth=True)
        kwargs = self._config.engine_kwargs(self._connect_args)
        try:
            # The coroutine must be created inside the lambda, since every
            # connection attempt needs a new coroutine.
            engine = create_async_engine(
                self._config.mock_url,
                async_creator=lambda: connector.connect_async(
                    self._config.instance_connection_name,
                    "asyncpg",
                    user=self._config.user,
                    db=self._config.database,
                    ip_type=IPTypes.PRIVATE,
                    **kwargs,
                ),
            )
        except Exception:
            await connector.close_async()
            raise
        self._connector = connector
        self._engine = engine
        return engine


class DatabaseEngineManager(EngineManager):
    """Manages a database engine and its associated resources.

    This class should be created via `engine_manager`, not directly.

    Parameters
    ----------
    config
        Connection configuration for the database.
    connect_args
        Additional connection arguments to pass directly to the underlying
        database driver.
    """

    def __init__(
        self, config: DatabaseSettings, connect_args: dict[str, Any] | None
    ) -> None:
        super().__init__(connect_args)
        self._config = config

    @override
    async def create_engine(self) -> AsyncEngine:
        if self._engine:
            raise RuntimeError("Call aclose before creating another engine")
        kwargs = self._config.engine_kwargs(self._connect_args)
        self._engine = create_async_engine(self._config.build_url(), **kwargs)
        return self._engine


def engine_manager(
    config: CloudSqlSettings | DatabaseSettings,
    connect_args: dict[str, Any] | None = None,
) -> EngineManager:
    """Create a database engine manager.

    config
        Database connection configuration.
    connect_args
        Additional connection arguments to pass directly to the underlying
        database driver.

    Returns
    -------
    EngineManager
        Engine manager that can be used to create an engine and clean up its
        associated resources when the caller is finished with the engine.
    """
    match config:
        case CloudSqlSettings():
            return CloudSqlEngineManager(config, connect_args)
        case DatabaseSettings():
            return DatabaseEngineManager(config, connect_args)
