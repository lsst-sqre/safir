"""Alembic support using an async database backend."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

try:
    import alembic
    from alembic import context
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import MetaData, text
    from sqlalchemy.engine import Connection
    from sqlalchemy.exc import ProgrammingError
    from sqlalchemy.ext.asyncio import AsyncEngine
except ImportError as e:
    raise ImportError(
        "The safir.database module requires the db extra. "
        "Install it with `pip install safir[db]`."
    ) from e
from pydantic import SecretStr
from pydantic_core import Url
from structlog.stdlib import BoundLogger

from ._connection import build_database_url, create_database_engine

__all__ = [
    "AlembicConfigError",
    "is_database_current",
    "run_migrations_offline",
    "run_migrations_online",
    "stamp_database",
    "stamp_database_async",
    "unstamp_database",
]


class AlembicConfigError(Exception):
    """The Alembic configuration was missing or invalid."""


async def is_database_current(
    engine: AsyncEngine,
    logger: BoundLogger | None = None,
    config_path: Path = Path("alembic.ini"),
) -> bool:
    """Check whether the database schema is at the current version.

    Every entry point to the application other than ones dedicated to updating
    the schema should normally call this function after creating the database
    engine and abort if it returns `False`.

    Parameters
    ----------
    engine
        Database engine to use.
    logger
        Logger to which the schema mismatch will be reported if the schema is
        out of date.
    config_path
        Path to the Alembic configuration.

    Returns
    -------
    bool
        `True` if Alembic reports the database schema is current, `False`
        otherwise.
    """

    def get_current_heads(connection: Connection) -> set[str]:
        context = MigrationContext.configure(connection)
        return set(context.get_current_heads())

    async with engine.begin() as connection:
        current = await connection.run_sync(get_current_heads)
    alembic_config = Config(str(config_path))
    alembic_scripts = ScriptDirectory.from_config(alembic_config)
    expected = set(alembic_scripts.get_heads())
    if current != expected:
        if logger:
            logger.error(
                f"Schema mismatch: {current} != {expected}",
                current_schema=list(current),
                expected_schema=list(expected),
            )
        return False
    else:
        return True


def run_migrations_offline(metadata: MetaData, url: str | Url) -> None:
    """Run Alembic migrations in offline mode.

    This function may only be called from the Alembic :file:`env.py` file.

    This configures the context with just a URL and not an engine. By skipping
    the engine creation, the DBAPI does not have to be available. The
    migrations are sent to the script output.

    Parameters
    ----------
    metadata
        Schema metadata object for the current schema.
    url
        Database connection URL.

    Examples
    --------
    Normally this is called from :file:`alembic/env.py` with code similar to
    the following:

    .. code-block:: python

       from alembic import context
       from safir.database import run_migrations_offline

       from example.config import config
       from example.schema import Base


       if context.is_offline_mode():
           run_migrations_offline(Base.metadata, config.database_url)
    """
    url = build_database_url(url, None, is_async=False)
    context.configure(
        url=url,
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online(
    metadata: MetaData,
    url: str | Url,
    password: str | SecretStr | None,
) -> None:
    """Run Alembic migrations online using an async backend.

    This function may only be called from the Alembic :file:`env.py` file.

    Parameters
    ----------
    metadata
        Schema metadata object for the current schema.
    url
        Database connection URL, not including the password.
    password
        Database connection password.

    Examples
    --------
    Normally this is called from :file:`alembic/env.py` with code similar to
    the following:

    .. code-block:: python

       from alembic import context
       from safir.database import run_migrations_offline

       from example.config import config
       from example.schema import Base


       if not context.is_offline_mode():
           run_migrations_online(
               Base.metadata, config.database_url, config.database_password
           )
    """

    def do_migrations(connection: Connection) -> None:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()

    async def run_async_migrations() -> None:
        engine = create_database_engine(url, password)
        async with engine.connect() as connection:
            await connection.run_sync(do_migrations)
        await engine.dispose()

    asyncio.run(run_async_migrations())


def stamp_database(config_path: Path) -> None:
    """Mark the database as updated to the head of the given Alembic config.

    Add the necessary data to the database to mark it as having the current
    schema, without performing any migrations. It is intended to be called
    immediately after a fresh database initialization with the current schema.

    Parameters
    ----------
    config_path
        Path to the Alembic configuration.
    """
    alembic.command.stamp(Config(str(config_path)), "head")


async def stamp_database_async(
    engine: AsyncEngine, config_path: Path = Path("alembic.ini")
) -> None:
    """Mark the database as updated to the head of the given Alembic config.

    Add the necessary data to the database to mark it as having the current
    schema, without performing any migrations. It is intended to be called
    immediately after a fresh database initialization with the current schema.

    The Alembic configuration must be :file:`alembic.ini` in the current
    directory, and contain correct pointers to the database migrations.

    If running outside of an event loop, use `stamp_database` instead.

    Parameters
    ----------
    engine
        Database engine to use.
    config_path
        Path to the Alembic configuration.

    Raises
    ------
    AlembicConfigError
        Raised if no migration heads could be found in the Alembic
        configuration.
    """
    alembic_config = Config(str(config_path))
    alembic_scripts = ScriptDirectory.from_config(alembic_config)
    current_head = alembic_scripts.get_current_head()
    if not current_head:
        raise AlembicConfigError("Unable to find head of Alembic migrations")

    def set_version(connection: Connection) -> None:
        context = MigrationContext.configure(connection)
        context.stamp(alembic_scripts, current_head)

    await unstamp_database(engine)
    async with engine.begin() as connection:
        await connection.run_sync(set_version)


async def unstamp_database(engine: AsyncEngine) -> None:
    """Clear the Alembic version from the database.

    This is done before stamping the database, or in test fixtures that are
    restoring a test database to an uninitialized state.

    Parameters
    ----------
    engine
        Engine to use for SQL calls.
    """
    async with engine.begin() as conn:
        with suppress(ProgrammingError):
            await conn.execute(text("DROP TABLE alembic_version"))
