"""Database initialization."""

from __future__ import annotations

import asyncio

try:
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.schema import CreateSchema
    from sqlalchemy.sql.schema import MetaData
except ImportError as e:
    raise ImportError(
        "The safir.database module requires the db extra. "
        "Install it with `pip install safir[db]`."
    ) from e
from structlog.stdlib import BoundLogger

from ._alembic import unstamp_database

__all__ = [
    "DatabaseInitializationError",
    "drop_database",
    "initialize_database",
]


class DatabaseInitializationError(Exception):
    """Database initialization failed."""


async def drop_database(engine: AsyncEngine, schema: MetaData) -> None:
    """Drop all tables from the database.

    Parameters
    ----------
    engine
        Engine to use to issue the SQL commands.
    schema
        Database ORM schema.
    """
    async with engine.begin() as conn:
        await conn.run_sync(schema.drop_all)
    await unstamp_database(engine)


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
