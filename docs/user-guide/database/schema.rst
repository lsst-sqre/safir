################
Managing schemas
################

The recommended way to manage application database schemas (including the schema used for the :doc:`UWS database </user-guide/uws/index>`) is Alembic_.
Safir provides some additional supporting functions to make using Alembic more straightforward and reliable.

These instructions assume that you have already defined your schema with SQLAlchemy's ORM model.
If you have not already done that, do that first.
For UWS applications that only have the UWS database, the declarative base of the schema is `safir.uws.UWSSchemaBase`.

Set up Alembic
==============

Alembic is not configured by default for the FastAPI template.
To use it, you will therefore need to set it up.

.. _database-alembic-config:

Add Alembic configuration
-------------------------

Add ``alembic[tz]`` as a runtime dependency for your package.
Then, in :file:`tox.ini`, add an ``alembic`` environment:

.. code-block:: toml
   :force:

   [testenv:alembic]
   description = Run Alembic against a test database
   commands =
       alembic {posargs}

Initialize the Alembic configuration:

.. prompt:: bash

   tox -e alembic -- init alembic

Replace :file:`alembic.ini` with the following:

.. code-block:: ini

   [alembic]
   script_location = %(here)s/alembic
   file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
   prepend_sys_path = .
   timezone = UTC
   version_path_separator = os

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
   from safir.logging import configure_alembic_logging, configure_logging

   from example.config import config
   from example.schema import Base

   # Configure structlog.
   configure_logging(name="example", log_level=config.log_level)
   configure_alembic_logging()

   # Run the migrations.
   if context.is_offline_mode():
       run_migrations_offline(Base.metadata, config.database_url)
   else:
       run_migrations_online(
           Base.metadata,
           config.database_url,
           config.database_password,
       )

Replace ``example`` with the module name and application name of your application as appropriate.
For applications that only use the UWS database, replace ``example.schema.Base`` in the above with `safir.uws.UWSSchemaBase`.

Add Alembic to the Docker image
-------------------------------

In the :file:`Dockerfile` for the application Docker image, when constructing the ``runtime-image`` layer, copy over the Alembic configuration so that it's present at runtime.

.. code-block:: docker
   :emphasize-lines: 9-14

   FROM base-image AS runtime-image

   # Create a non-root user
   RUN useradd --create-home appuser

   # Copy the virtualenv.
   COPY --from=install-image /opt/venv /opt/venv

   # Copy the Alembic configuration and migrations, and set that path as the
   # working directory so that Alembic can be run with a simple entry command
   # and no extra configuration.
   COPY --from=install-image /workdir/alembic.ini /app/alembic.ini
   COPY --from=install-image /workdir/alembic /app/alembic
   WORKDIR /app

Add Alembic to database initialization
--------------------------------------

If you used the pattern in :ref:`database-init-cli`, you will have an ``init`` command defined that initializes a new database.
To work properly with Alembic, that initialization should stamp the database with the current Alembic version after initialization.

Modify that initialization code as follows:

.. code-block:: python
   :emphasize-lines: 7,18-24,29,38

   import click
   import structlog
   from safir.asyncio import run_with_asyncio
   from safir.database import (
       create_database_engine,
       initialize_database,
       stamp_database,
   )

   from .config import config
   from .schema import Base


   # Definition of main omitted.


   @main.command()
   @click.option(
       "--alembic-config-path",
       envvar="EXAMPLE_ALEMBIC_CONFIG_PATH",
       type=click.Path(path_type=Path),
       default=Path("/app/alembic.ini"),
       help="Alembic configuration file.",
   )
   @click.option(
       "--reset", is_flag=True, help="Delete all existing database data."
   )
   @run_with_asyncio
   async def init(*, alembic_config_path: Path, reset: bool) -> None:
       logger = structlog.get_logger(config.logger_name)
       engine = create_database_engine(
           config.database_url, config.database_password
       )
       await initialize_database(
           engine, logger, schema=Base.metadata, reset=reset
       )
       await engine.dispose()
       stamp_database(alembic_config_path)

Change ``EXAMPLE`` to the environment variable prefix used for configuration settings for your application.

.. _database-alembic-commands:

Add commands to update and validate schema
------------------------------------------

To run any necessary migrations to update the schema to the current version, all you need to do is run :command:`alembic upgrade head` from the directory containing :file:`alembic.ini`.
You may, however, find it useful to have a simple command in your application to do this, particularly if you have any additional application-specific checks you want to do.

Here is a simple starting point:

.. code-block:: python

   import subprocess
   from pathlib import Path

   import click


   # Definition of main omitted.


   @main.command()
   @click.option(
       "--alembic-config-path",
       envvar="EXAMPLE_ALEMBIC_CONFIG_PATH",
       type=click.Path(path_type=Path),
       default=Path("/app/alembic.ini"),
       help="Alembic configuration file.",
   )
   def update_schema(*, alembic_config_path: Path) -> None:
       """Update the schema."""
       subprocess.run(
           ["alembic", "upgrade", "head"],
           check=True,
           cwd=str(alembic_config_path.parent),
       )

You can add on to this framework.
For example, if you have a method that checks whether the database already exists (by, for instance, getting the first row of some table), you can run that check first and initialize the database instead if it doesn't exist at all.

You may also find it useful to have a command that checks the current schema and reports whether it is up to date.
Here is one way to implement that:

.. code-block:: python

   from pathlib import Path

   import click
   import structlog
   from safir.asyncio import run_with_asyncio
   from safir.database import create_database_engine, is_database_current

   from .config import config


   # Definition of main omitted.


   @main.command()
   @run_with_asyncio
   async def validate_schema(*, alembic_config_path: Path) -> None:
       """Validate that the database schema is current."""
       engine = create_database_engine(
           config.database_url, config.database_password
       )
       logger = structlog.get_logger("example")
       if not await is_database_current(engine, logger, alembic_config_path):
           raise click.ClickException("Database schema is not current")

Add Alembic checks to startup
-----------------------------

The application should check whether the database schema is up to date when starting.

First, if the application currently runs database initialization during startup, delete that.
Usually this is via a command like ``example init`` in :file:`scripts/start.sh`.
Delete any line like that.

Then, in :file:`main.py`, add code to check the database schema in the application's lifespan hook before initializing the database session dependency.

.. code-block:: python
   :emphasize-lines: 4,5,14-20

   from collections.abc import AsyncIterator
   from contextlib import asynccontextmanager

   import structlog
   from fastapi import FastAPI
   from safir.database import create_database_engine, is_database_current
   from safir.dependencies.db_session import db_session_dependency

   from .config import config


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncIterator[None]:
       logger = structlog.get_logger("example")
       engine = create_database_engine(
           config.database_url, config.database_password
       )
       if not await is_database_current(engine, logger):
           raise RuntimeError("Database schema out of date")
       await engine.dispose()
       await db_session_dependency.initialize(
           config.database_url, config.database_password
       )
       yield
       await db_session_dependency.aclose()


   app = FastAPI(lifespan=lifespan)

If the database schema is out of date, the application will now refuse to start.
You may wish to define a custom exception for this problem rather than using `RuntimeError`.

If the application has any other entry points that use the database — other CLI commands, Kubernetes operators, or arq_ workers, for example — all of those entry points should include similar code to check the database schema before any operation that uses the database.

Add Alembic to the test suite
-----------------------------

In the test suite fixtures (generally in :file:`tests/conftest.py`), integrating Alembic requires stamping the database after initializing it.
This ensures that the checks for the schema will pass when executing tests.

.. code-block:: python
   :emphasize-lines: 9,26

   from collections.abc import AsyncIterator

   import pytest_asyncio
   from asgi_lifespan import LifespanManager
   from fastapi import FastAPI
   from safir.database import (
       create_database_engine,
       initialize_database,
       stamp_database_async,
   )

   from example import main
   from example.config import config
   from example.schema import Base


   @pytest_asyncio.fixture
   async def app() -> AsyncIterator[FastAPI]:
       logger = structlog.get_logger(config.logger_name)
       engine = create_database_engine(
           config.database_url, config.database_password
       )
       await initialize_database(
           engine, logger, schema=Base.metadata, reset=True
       )
       await stamp_database_async(engine)
       await engine.dispose()
       async with LifespanManager(main.app):
           yield main.app

When cleaning out the test database between tests, call `~safir.database.unstamp_database` after dropping the application's database tables if you want to fully reset the database to its state before running the test.
The ``reset=True`` flag of `~safir.database.initialize_database` does not do this.

Creating database migrations
============================

Whenever the database schema changes, you will need to create an Alembic migration.

Add a docker-compose configuration
----------------------------------

To create a database migration, you'll need to initialize a database with the current version of the schema and then generate a migration using the new version of the schema.
This requires a running database that can be used with two different versions of the source tree.

The easiest way to do this is with the command :command:`docker-compose`.
Create a :file:`alembic/docker-compose.yaml` file that looks something like this:

.. code-block:: yaml

   version: "3"
   services:
     postgresql:
       image: "postgres:latest"
       hostname: "postgresql"
       container_name: "postgresql"
       environment:
         POSTGRES_PASSWORD: "INSECURE"
         POSTGRES_USER: "example"
         POSTGRES_DB: "example"
       ports:
         - "5432:5432"

Change the user and database names to match your application.
If your application also requires other running services, such as Redis, in order to start, you may need to set up those containers as well.

Add tox settings for the Alembic environment
--------------------------------------------

In :ref:`database-alembic-config`, you created an ``alembic`` tox environment.
Add the environment variable settings to that environment that tell your application to use the PostgreSQL instance started by :command:`docker-compose`:

.. code-block:: toml
   :force:

   [testenv:alembic]
   description = Run Alembic against a test database
   commands =
       alembic {posargs}
   setenv =
       EXAMPLE_DATABASE_URL = postgresql://example@localhost/example
       EXAMPLE_DATABASE_PASSWORD = INSECURE

Change the database name, username, and environment variable prefix to match your application.

You will also need a tox environment that runs your application.
This will look something like the following:

.. code-block:: toml
   :force:

   [testenv:example]
   description = Run command-line tool against a test database
   commands =
       example {posargs}
   setenv =
       EXAMPLE_ALEMBIC_CONFIG_PATH = {toxinidir}/alembic.ini
       EXAMPLE_DATABASE_URL = postgresql://example@localhost/example
       EXAMPLE_DATABASE_PASSWORD = INSECURE

As above, change the database name, username, command name, and environment variable prefix to match your application.

Create the migration
--------------------

You're now ready to create the database migration.

#. Start a PostgreSQL server into which the current database schema can be created.

   .. prompt:: bash

      docker-compose -f alembic/docker-compose.yaml up

#. Install the *current* database schema into that PostgreSQL server.
   This must be done with a working tree that does not contain any changes to the database schema.
   If you have already made changes that would change the database schema, use :command:`git stash`, switch to another branch, or otherwise temporarily revert those changes before running this command.

   .. prompt:: bash

      tox run -e example -- init

   Change the environment to match the one you created above.

#. Apply the code changes that will change the database schema.

#. Ask Alembic to autogenerate a database migration to the new schema.

   .. prompt:: bash

      tox run -e alembic -- revision --autogenerate -m "<message>"

   Replace ``<message>`` with a short human-readable summary of the change, ending in a period.
   This will create a new file in :file:`alembic/versions`.

#. Edit the created file in :file:`alembic/versions` and adjust it as necessary.
   See the `Alembic documentation <https://alembic.sqlalchemy.org/en/latest/autogenerate.html>`__ for details about what Alembic can and cannot autodetect.

   One common change that Alembic cannot autodetect is changes to the valid values of enum types.
   You will need to add Alembic code to the ``upgrade`` function of the migration such as:

   .. code-block:: python

      op.execute("ALTER TYPE tokentype ADD VALUE 'oidc' IF NOT EXISTS")

   You may want to connect to the PostgreSQL database with the :command:`psql` command-line tool so that you can examine the schema to understand what the migration needs to do.
   For example, you can see a description of a table with :samp:`\d {table}`, which will tell you the name of an enum type that you may need to modify.
   To do this, run:

   .. prompt:: bash

      psql <uri>

   where ``<uri>`` is the URI to the local PostgreSQL database, which you can find in the ``databaseUrl`` configuration parameter in :file:`alembic/gafaelfawr.yaml`.

#. Stop the running PostgreSQL container.

   .. prompt:: bash

      docker-compose -f alembic/docker-compose.yaml down

Applying database migrations
============================

Finally, you have to arrange for database migrations to be applied to your application.

One option is to not add any special code to do this and instead do it manually when needed.
Database migrations are rare, so this may be a reasonable approach.
You will need to start a Kubernetes pod with your new application source, including the new schema, where you can run the ``update-schema`` command added in :ref:`database-alembic-commands`.

The more automated option is to create a Helm hook that creates a Kubernetes ``Job`` to run the ``update-schema`` command before syncing the rest of the application.
It's usually best to make this conditional on a configuration option being set so that database schema upgrades aren't automatically done on every Helm deployment.

The details of how to set up this Helm hook will depend on the details of your application and what configuration it needs, but the basic idea is to add a ``Job`` resource, conditional on the ``updateSchema`` Helm values option being set, that runs the ``update-schema`` command.
Applications that use CloudSQL will need some special support for running the CloudSQL sidedar.

See `the Gafaelfawr Helm chart in Phalanx <https://github.com/lsst-sqre/phalanx/tree/main/applications/gafaelfawr>`__ for an example.
