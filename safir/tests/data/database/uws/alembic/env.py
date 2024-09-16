"""Alembic migration environment.

Keep in sync with the instructions in the Safir user guide.
"""

from alembic import context

from safir.database import run_migrations_offline, run_migrations_online
from safir.logging import configure_alembic_logging, configure_logging
from safir.uws import UWSSchemaBase
from tests.support.alembic import config

# Configure structlog.
configure_logging(name="tests", log_level=config.log_level)
configure_alembic_logging()

# Run the migrations.
if context.is_offline_mode():
    run_migrations_offline(UWSSchemaBase.metadata, config.database_url)
else:
    run_migrations_online(
        UWSSchemaBase.metadata,
        config.database_url,
        config.database_password,
    )
