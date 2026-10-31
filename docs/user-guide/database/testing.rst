:og:description: Learn how to use test applications that use a database.

.. py:currentmodule:: safir.database

########################################
Testing applications that use a database
########################################

The recommended strategy for testing applications that use a database is to start a real PostgreSQL server for the tests.
While support for SQLite could be added, testing against the database that will be used for production is usually a better strategy, since some bugs (particularly around transaction management) are sensitive to the choice of backend.

Starting the database for tests
===============================

There are two ways to start the database used by the test suite: manage it in nox_, or manage it using test fixtures.
Starting the database in nox is usually preferred, since :file:`noxfile.py` needs the ability to start the PostgreSQL server anyway to generate Alembic schema migrations.

Starting the database with nox
------------------------------

First, ensure that you've already added the :ref:`configuration required by Alembic <database-alembic-nox>` to your :file:`noxfile.py`.
The same code will be reused to start the database for the test suite.

Then, all you should need to do is use the ``_start_containers`` context manager for the ``test`` nox session, similar to how it's used for the ``create-migration`` nox session.
For example:

.. code-block:: python

   @session(uv_groups=["dev"])
   def test(session: nox.Session) -> None:
       """Test the example application."""
       with _start_containers() as containers:
           session.run(
               "pytest",
               "--cov=example",
               "--cov-branch",
               "--cov-report=",
               *session.posargs,
           )

Change all occurrences of ``example`` to something appropriate for your application.
The ``_start_containers`` decorator defined in :ref:`database-alembic-nox` sets the appropriate environment variables to inject the database username and password into the configuration.

Using the database in tests
===========================

Since :file:`noxfile.py` defines the appropriate environment variables, your application should pick up the URL and password for the database through its normal configuration mechanism.
Nothing special is therefore required to connect to the database.

However, normally the application will not attempt to initialize the database on every startup, since this is potentially undesirable in production deployments.
Each test should also start with an empty database state so that tests do not interfere with subsequent tests.
You should therefore create a fixture that reinitializes the database for each test.
Conventially, this fixture is named ``empty_database`` and uses an ``engine`` fixture to create the database engine.

.. code-block:: python
   :caption: tests/conftest.py

   from collections.abc import AsyncGenerator

   import pytest_asyncio
   import structlog
   from safir.database import (
       engine_manager,
       iniitalize_database,
       stamp_database_async,
   )
   from sqlalchemy.ext.asyncio import AsyncEngine

   from example.schema import SchemaBase


   @pytest_asyncio.fixture
   async def engine(config: Config) -> AsyncGenerator[AsyncEngine]:
       async with engine_manager(config.database) as engine:
           yield engine


   @pytest_asyncio.fixture
   async def empty_database(engine: AsyncEngine) -> None:
       logger = structlog.get_logger(__file__)
       schema = SchemaBase.metadata
       await initialize_database(engine, logger, schema=schema, reset=True)
       await stamp_database_async(engine)

As always, replace any instances of ``example`` with what is appropriate for your application.

This drops and recreates all tables between each test and ensures that the Alembic version information is correctly set so that schema checks run by the application during startup will pass.

This example assumes that you have a fixture named ``config`` that returns the application configuration.
This is a common pattern for applications that use YAML configuration files (see :doc:`/user-guilde/config`).
If your application uses a global ``config`` object initialized from environment variables, import that instead of using a ``config`` fixture.

Once these fixtures are in place, any test or fixture that needs an initialized, empty database can request on the ``empty_database`` fixture.
Usually you will want to do that in the ``app`` fixture.
Alternately, if nearly every test uses the database anyway, you can mark the fixture autouse.
Tests that need a connected database engine can request the ``engine`` fixture.

.. warning::

   Because these fixtures set up a single external PostgreSQL instance with a single database, tests cannot be run in parallel, or a test may see database changes from another test.
   This, in turn, means that plugins like `pytest-xdist <https://pypi.org/project/pytest-xdist/>`__ unfortunately cannot be used to speed up tests.
   With some additional effort, not documented here, you can work around this by using per-test databases or database schemas.

.. _database-testing-alembic:

Testing database migrations
===========================

You will want to test that you do not accidentally introduce a database schema change.

The easiest way to do this is to add a schema test that fails if the schema created by applying all Alembic migrations does not match the current SQLAlchemy ORM schema definition.
This will require adding an Alembic migration at the same time as a schema change, which is the recommended development approach.

The following test can be dropped into :file:`tests/schema_test.py` and should work for most applications that follow the Safir documentation.

.. code-block:: python

   import os
   import subprocess

   import pytest
   from safir.database import drop_database, engine_manager

   from example.config import Config
   from example.dependencies.config import config_dependency
   from example.schema import SchemaBase


   @pytest.mark.asyncio
   async def test_schema(config: Config) -> None:
       async with engine_manager(config.database) as engine:
           await drop_database(engine, SchemaBase.metadata)
       config_path = str(config_dependency.config_path)
       env = {**os.environ, "EXAMPLE_CONFIG_PATH": config_path}
       subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
       subprocess.run(["alembic", "check"], check=True, env=env)

As always, replace ``example`` and ``EXAMPLE`` with the appropriate values for your application.

As above, this example assumes that you have a fixture named ``config`` that returns the application configuration.
If your application uses a global ``config`` object initialized from environment variables, import that instead of using a ``config`` fixture.

.. warning::

   This test can only catch schema changes that Alembic knows how to generate migrations for.
   Changes that Alembic misses, such as changes to the membership of an enum, will not be caught by this test.
