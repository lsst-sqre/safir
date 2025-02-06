########################################
Testing applications that use a database
########################################

The Safir database layer only supports PostgreSQL at present.
While support for SQLite could be added, testing against the database that will be used for production is usually a better strategy, since some bugs (particularly around transaction management) are sensitive to the choice of backend.

The recommended strategy for testing applications that use a database is to start a real PostgreSQL server for the tests.

Also see :ref:`database-alembic-testing` for information on how to test Alembic schema management.

Using tox-docker
================

One approach to starting a test database is to use the tox-docker_ plugin for tox_.

Configure tox-docker
--------------------

To do this, add ``tox-docker`` to :file:`requirements/tox.in` and run :command:`make update`.
Then, add the following to :file:`tox.ini` to define a database container:

.. code-block:: ini

   [docker:postgres]
   image = postgres:latest
   ports =
       5432:5432/tcp
   environment =
       POSTGRES_PASSWORD = INSECURE-PASSWORD
       POSTGRES_USER = example
       POSTGRES_DB = example
       PGPORT = 5432
   # The healthcheck ensures that tox-docker won't run tests until the
   # container is up and the command finishes with exit code 0 (success)
   healthcheck_cmd = PGPASSWORD=$POSTGRES_PASSWORD psql  \
       --user=$POSTGRES_USER --dbname=$POSTGRES_DB       \
       --host=127.0.0.1 --quiet --no-align --tuples-only \
       -1 --command="SELECT 1"
   healthcheck_timeout = 1
   healthcheck_retries = 30
   healthcheck_interval = 1
   healthcheck_start_period = 1

Change ``POSTGRES_USER`` and ``POSTGRES_DB`` to match the name of your application.

Add a dependency on this container to your ``py`` test environment (and any other tox environments that will run :command:`pytest`):

.. code-block:: ini

   [testenv:py]
   # ...
   docker =
       postgres

You may want to also add this to any ``run`` test environment you have defined so that a PostgreSQL container will be started for the local development environment.

Pass database details to the application
----------------------------------------

Assuming that your application uses environment variables to configure the database URL and password (the recommended approach), set those environment variables in the ``py`` test environment (and any other relevant test environments, such as ``run``):

.. code-block:: ini

   [testenv:py]
   # ...
   setenv =
       EXAMPLE_DATABASE_URL = postgresql://safir@127.0.0.1/safir
       EXAMPLE_DATABASE_PASSWORD = INSECURE-PASSWORD

Change the names of the environment variables to match those used by your application, and change the database user and database name to match your application if you did so in the ``[docker:postgres]`` section.

Your application should declare the database URL in the configuration to have the Pydantic type `~safir.pydantic.EnvAsyncPostgresDsn` (see :ref:`pydantic-dsns`).
This will automatically pick up the IP address and port of the test database from environment variables set by tox-docker_ and adjust the URL accordingly when the configuration is parsed.

Use the database in tests
-------------------------

Initialize the database in a test fixture.
The simplest way to do this is to add a call to `~safir.database.initialize_database` to the ``app`` fixture.
For example:

.. code-block:: python

   from collections.abc import AsyncGenerator

   import pytest_asyncio
   from asgi_lifespan import LifespanManager
   from fastapi import FastAPI
   from safir.database import create_database_engine, initialize_database

   from example import main
   from example.config import config
   from example.schema import Base


   @pytest_asyncio.fixture
   async def app() -> AsyncGenerator[FastAPI]:
       logger = structlog.get_logger(config.logger_name)
       engine = create_database_engine(
           config.database_url, config.database_password
       )
       await initialize_database(
           engine, logger, schema=Base.metadata, reset=True
       )
       await engine.dispose()
       async with LifespanManager(main.app):
           yield main.app

This uses the ``reset`` flag to drop and recreate all database tables between each test, which ensures no test records leak from one test to the next.

If you need to preload test data into the database, do that after the call to ``initialize_database`` and before ``await engine.dispose()``, using the provided engine object.

.. warning::

   Because the tests use a single external PostgreSQL instance with a single database, tests cannot be run in parallel, or a test may see database changes from another test.
   This, in turn, means that plugins like `pytest-xdist <https://pypi.org/project/pytest-xdist/>`__ unfortunately cannot be used to speed up tests.
