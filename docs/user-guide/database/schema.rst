:og:description: Learn how to manage database schemas with Safir.

.. py:currentmodule:: safir.database

################
Managing schemas
################

The recommended way to manage application database schemas (including the schema used for the :doc:`UWS database </user-guide/uws/index>`) is Alembic_.
Safir provides some additional supporting functions to make using Alembic more straightforward and reliable.

Define the database schema
==========================

Safir's database support assumes that the application has defined the database schema via the SQLAlchemy ORM.
The recommended way to do this is to add a ``schema`` directory to the application containing the table definitions.

In the file :file:`schema/_base.py`, define the SQLAlchemy declarative base:

.. code-block:: python

   from sqlalchemy.orm import DeclarativeBase


   class SchemaBase(DeclarativeBase):
       """Declarative base for SQLAlchemy ORM model of database schema."""

In other files in that directory, define the database tables using the `normal SQLAlchemy ORM syntax <https://docs.sqlalchemy.org/en/latest/orm/mapping_styles.html#declarative-mapping>`__, one table per file.
Each database table definition must inherit from ``SchemaBase``, imported from ``._base``.

In :file:`schema/__init__.py`, import the table definitions from all of the files in the directory, as well as the ``Base`` class, and export them using ``__all__``.

Using non-default PostgreSQL schemas
------------------------------------

Sometimes it is convenient for multiple applications to share the same database but use separate collections of tables.
PostgreSQL supports serving multiple schemas (in the sense of a namespace of tables) from the same database, and SQLAlchemy supports specifying the PostgreSQL schema for a given collection of tables.

The normal way to do this in SQLAlchemy is to modify the `~sqlalchemy.orm.DeclarativeBase` subclass used by the table definitions to specify a non-default schema.
For example:

.. code-block:: python

   from sqlalchemy import MetaData
   from sqlalchemy.orm import DeclarativeBase

   from ..config import config


   class SchemaBase(DeclarativeBase):
       metadata = MetaData(schema=config.database_schema)

If ``config.database_schema`` is `None`, the default schema will be used; otherwise, SQLAlchemy will use the specified schema instead of the default one.

Safir supports this in database initialization by creating a non-default schema if one is set.
If the ``schema`` attribute is set (via code like the above) on the SQLAlchemy metadata passed to the ``schema`` parameter of `~safir.database.initialize_database`, it will create that schema in the PostgreSQL database if it does not already exist.

Set up Alembic
==============

Alembic is not configured by default for the FastAPI template.
To use it, you will therefore need to set it up.

.. _database-alembic-config:

Add Alembic configuration
-------------------------

Add ``alembic[tz]`` as a runtime dependency for your package.
Update the development virtualenv with :command:`make update`.
Then, initialize the Alembic configuration with:

.. prompt:: bash

   uv run alembic init alembic

Replace :file:`alembic.ini` with the following:

.. code-block:: ini

   [alembic]
   script_location = %(here)s/alembic
   file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
   path_separator = os
   prepend_sys_path = .
   timezone = UTC

   [post_write_hooks]
   hooks = ruff ruff_format
   ruff.type = exec
   ruff.executable = ruff
   ruff.options = check --fix REVISION_SCRIPT_FILENAME
   ruff_format.type = exec
   ruff_format.executable = ruff
   ruff_format.options = format REVISION_SCRIPT_FILENAME

Replace :file:`alembic/env.py` with the following:

.. code-block:: python

   """Alembic migration environment."""

   from alembic import context
   from safir.database import run_migrations_offline, run_migrations_online
   from safir.logging import configure_alembic_logging

   from example.dependencies.config import config_dependency
   from example.schema import SchemaBase

   config = config_dependency.config()
   configure_alembic_logging()
   if context.is_offline_mode():
       run_migrations_offline(SchemaBase.metadata, config.database.mock_url)
   else:
       run_migrations_online(SchemaBase.metadata, config.database)

Replace ``example`` with the module name and application name of your application as appropriate.

Add Alembic to the Docker image
-------------------------------

In the :file:`Dockerfile` for the application Docker image, when constructing the ``runtime-image`` layer, copy over the Alembic configuration so that it's present at runtime.

.. code-block:: docker
   :emphasize-lines: 9-14

   FROM base-image AS runtime-image

   # Create a non-root user
   RUN useradd --create-home appuser

   # Copy the virtualenv.
   COPY --from=install-image /app/.venv /app/.venv

   # Copy the Alembic configuration and migrations, and set that path as the
   # working directory so that Alembic can be run with a simple entry command
   # and no extra configuration.
   COPY --from=install-image /app/alembic /app/alembic
   COPY --from=install-image /app/alembic.ini /app/alembic.ini
   WORKDIR /app

.. _database-alembic-commands:

Add commands to update and validate schema
==========================================

To run any necessary migrations to update the schema to the current version, all you need to do is run :command:`alembic upgrade head` from the directory containing :file:`alembic.ini`.
You may, however, find it useful to have a simple command in your application to do this, particularly if you have any additional application-specific checks you want to do.

Here is a command to upgrade or create a database schema as appropriate:

.. code-block:: python

   import subprocess
   from pathlib import Path

   import click

   # Definition of main omitted.


   @main.command()
   @click.option(
       "--config-path",
       envvar="EXAMPLE_CONFIG_PATH",
       type=click.Path(path_type=Path),
       default=None,
       help="Application configuration file.",
   )
   def update_schema(*, config_path: Path | None) -> None:
       """Update the schema."""
       if config_path:
           env = {**os.environ, "EXAMPLE_CONFIG_PATH": str(config_path)}
       else:
           env = None
       subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)

Change ``EXAMPLE`` to something appropriate for your application.
If you have other upgrade or migration code that needs to run, you can add it to this function.

You may also find it useful to have a command that checks the current schema and reports whether it is up to date.
Here is one way to implement that:

.. code-block:: python

   from pathlib import Path

   import click
   import structlog
   from safir.asyncio import run_with_asyncio
   from safir.database import engine_manager, is_database_current

   from .dependencies.config import config_dependency

   # Definition of main omitted.


   @main.command()
   @click.option(
       "--config-path",
       envvar="EXAMPLE_CONFIG_PATH",
       type=click.Path(path_type=Path),
       default=None,
       help="Application configuration file.",
   )
   @run_with_asyncio
   async def validate_schema(*, config_path: Path | None) -> None:
       """Validate that the database schema is current."""
       if config_path:
           config_dependency.set_config_path(config_path)
       config = config_dependency.config()
       logger = structlog.get_logger("example")

       async with engine_manager(config.database) as engine:
           if not await is_database_current(engine, logger):
               raise click.ClickException("Database schema is not current")

Add Alembic checks to startup
=============================

The application should check whether the database schema is up to date when starting.
This is discussed as part of the broader topic of :doc:`database engine creation <engine>`.

.. _database-alembic-nox:

Integrate Alembic with nox
==========================

The way Alembic works is that every change to the database schema is represented by a database migration.
Those migrations are collected in the :file:`alembic/versions` directory and applied as needed to convert the database to the latest schema.

The easiest way to create those migrations in a Safir-based project is to add a ``create-migration`` session to the project nox configuration.
This requires a bit of infrastructure to start a test PostgreSQL container that will be used by the nox session to calculate the changes to the schema from the most recent Alembic state.

Add the following to :file:`noxfile.py`:

.. code-block:: python

   import logging
   import os
   from collections.abc import Iterator
   from contextlib import contextmanager
   from dataclasses import dataclass
   from pathlib import Path

   import nox
   from nox_uv import session
   from testcontainers.postgres import PostgresContainer

   # PostgreSQL image to use for testing.
   POSTGRES_IMAGE = "postgres:18"


   @dataclass
   class _Containers:
       env: dict[str, str]
       postgres: PostgresContainer


   @contextmanager
   def _start_containers() -> Iterator[_Containers]:
       alembic_path = Path(__file__).parent / "alembic.ini"
       env = {"EXAMPLE_ALEMBIC_CONFIG_PATH": str(alembic_path)}
       logging.getLogger("docker").setLevel(logging.INFO)
       logging.getLogger("testcontainers").setLevel(logging.INFO)
       logging.getLogger("urllib3").setLevel(logging.INFO)
       with PostgresContainer(
           image=POSTGRES_IMAGE,
           driver="asyncpg",
           dbname="semaphore",
           username="semaphore",
           password=os.urandom(16).hex(),
       ) as postgres:
           env["EXAMPLE_DATABASE__PASSWORD"] = postgres.password
           env["EXAMPLE_DATABASE__URL"] = postgres.get_connection_url()
           yield _Containers(env=env, postgres=postgres)


   @session(name="create-migration", uv_groups=["dev"])
   def create_migration(session: nox.Session) -> None:
       """Create a database schema migration to the current schema."""
       message = session.posargs[0] if session.posargs else "Autogenerated"
       with _start_containers() as containers:
           session.run("alembic", "upgrade", "head", env=env)
           session.run(
               "alembic",
               "revision",
               "--autogenerate",
               "-m",
               message,
               env=containers.env,
           )

This code assumes you are using the configuration approach described in :doc:`config`.
As always, replace ``EXAMPLE`` with the appropriate prefix for your application.

You can now run :command:`nox -s create-migration` to create a new Alembic migration reflecting changes to the database schema since the last Alembic migration.

Create the initial Alembic migration
====================================

Alembic works more smoothly if the first release of the service has an initial database migration, at the head of the migration dependency chain, that creates the full database schema.
You should therefore generate an Alembic database migration from an empty database once you've configured Alembic for the first time.

If you have written the SQLAlchemy schema for your application and configured Alembic and nox as described above, this should require nothing more than:

.. prompt:: bash

   nox -s create-migration

Creating database migrations
============================

Whenever the database schema changes, you will need to create an Alembic migration.

First, change the SQLAlchemy schema to reflect the new desired database schema and thoroughly test your change.
Then, run:

.. prompt:: bash

   nox -s create-migration

Finally, edit the created file in :file:`alembic/versions` and adjust it as necessary.
See the `Alembic documentation <https://alembic.sqlalchemy.org/en/latest/autogenerate.html>`__ for details about what Alembic can and cannot autodetect.

One common change that Alembic cannot autodetect is changes to the valid values of enum types.
You will need to add Alembic code to the ``upgrade`` function of the migration such as:

.. code-block:: python

   op.execute("ALTER TYPE tokentype ADD VALUE 'oidc' IF NOT EXISTS")

Applying database migrations
============================

Finally, you have to arrange for database migrations to be applied to your application.

One option is to not add any special code to do this and instead do it manually when needed.
Database migrations are rare, so this may be a reasonable approach.
You will need to start a Kubernetes pod with your new application source, including the new schema, where you can run the ``update-schema`` command added in :ref:`database-alembic-commands`.

The more automated option is to create a Helm hook that creates a Kubernetes ``Job`` to run the ``update-schema`` command before syncing the rest of the application.
It's usually best to make this conditional on a configuration option being set so that database schema upgrades aren't automatically done on every Helm deployment.

The details of how to set up this Helm hook will depend on the details of your application and what configuration it needs, but the basic idea is to add a ``Job`` resource, conditional on the ``updateSchema`` Helm values option being set, that runs the ``update-schema`` command.

See `the Gafaelfawr Helm chart in Phalanx <https://github.com/lsst-sqre/phalanx/tree/main/applications/gafaelfawr>`__ for an example.
