"""Test UWS integration with Alembic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from structlog.stdlib import BoundLogger

from safir.uws import DatabaseSchemaError, UWSApplication, UWSConfig


@pytest.mark.asyncio
async def test_database_init(
    uws_config: UWSConfig, logger: BoundLogger
) -> None:
    uws = UWSApplication(uws_config)
    config_path = (
        Path(__file__).parent.parent
        / "data"
        / "database"
        / "uws"
        / "alembic.ini"
    )
    worker_settings = uws.build_worker(
        logger, check_schema=True, alembic_config_path=config_path
    )
    assert worker_settings.on_startup
    assert worker_settings.on_shutdown
    worker_ctx: dict[Any, Any] = {}
    worker_startup = worker_settings.on_startup
    worker_shutdown = worker_settings.on_shutdown

    # Initialize the database without Alembic.
    await uws.initialize_uws_database(logger, reset=True)

    # Initializing a FastAPI app, or creating a UWS worker, should both fail
    # because the database is not current.
    assert not await uws.is_schema_current(logger, config_path)
    with pytest.raises(DatabaseSchemaError):
        await uws.initialize_fastapi(
            logger, check_schema=True, alembic_config_path=config_path
        )
    with pytest.raises(DatabaseSchemaError):
        await worker_startup(worker_ctx)

    # Reinitialize the database with Alembic.
    await uws.initialize_uws_database(
        logger,
        reset=True,
        use_alembic=True,
        alembic_config_path=config_path,
    )

    # Other initializations should now succeed.
    assert await uws.is_schema_current(logger, config_path)
    await uws.initialize_fastapi(
        logger, check_schema=True, alembic_config_path=config_path
    )
    await worker_startup(worker_ctx)

    # Clean up those initializations.
    await uws.shutdown_fastapi()
    await worker_shutdown(worker_ctx)
