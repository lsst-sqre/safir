######################
Using the database API
######################

Safir-based applications that use a SQL database can use Safir to initialize that database and acquire a database session.
Safir-based applications that use FastAPI can also use the Safir-provided FastAPI dependency to manage per-request database sessions.
The Safir database support is based on `SQLAlchemy`_ and assumes use of PostgreSQL (possibly via `Cloud SQL <https://cloud.google.com/sql>`__) as the underlying database.

Safir is an asyncio framework and thus encourages use of the asyncio support in SQLAlchemy.
This requires using the `SQLAlchemy 2.0 API <https://docs.sqlalchemy.org/en/14/tutorial/index.html>`__, which is somewhat different than the older API.
Safir uses the `asyncpg`_ PostgreSQL database driver.

Database support in Safir is optional.
To use it, depend on ``safir[db]`` in your pip requirements.

Initializing a database
=======================

Safir supports simple initialization of a database with a schema provided by the application.
By default, this only adds any declared but missing tables, indices, or other objects, and thus does nothing if the database is already initialized.
The application may also request a database reset, which will drop and recreate all of the tables in the schema.

More complex database schema upgrades are not supported by Safir.
If those are required, consider using `Alembic <https://alembic.sqlalchemy.org/en/latest/>`__.

Database initialization in Safir assumes that the application has defined the database schema via the SQLAlchemy ORM.
The recommended way to do this is to add a ``schema`` directory to the application containing the table definitions.
In the file ``schema/base.py``, define the SQLAlchemy declarative base:

.. code-block:: python

   from sqlalchemy.orm import declarative_base

   Base = declarative_base()

In other files in that directory, define the database tables using the normal SQLAlchemy ORM syntax, one table per file.
Each database table definition must inherit from ``Base``, imported from ``.base``.
In ``schema/__init__.py``, import the table definitions from all of the files in the directory, as well as the ``Base`` variable, and export them using ``__all__``.

The recommended approach to add database initialization to an application is to add an ``init`` command to the command-line interface that runs the database initialization code.
For applications using `Click`_ (the recommended way to implement a command-line interface), this can be done with code like:

.. code-block:: python

   import click
   import structlog
   from safir.asyncio import run_with_asyncio
   from safir.database import create_database_engine, initialize_database

   from .config import config
   from .schema import Base


   # Definition of main omitted.


   @main.command()
   @click.option(
       "--reset", is_flag=True, help="Delete all existing database data."
   )
   @run_with_asyncio
   async def init(reset: bool) -> None:
       logger = structlog.get_logger(config.logger_name)
       engine = create_database_engine(
           config.database_url, config.database_password
       )
       await initialize_database(
           engine, logger, schema=Base.metadata, reset=reset
       )
       await engine.dispose()

This code assumes that ``main`` is the Click entry point and ``.config`` provides a ``config`` object that contains the settings for the application, including the database URL and password as well as the normal Safir configuration settings.

If it receives a connection error from the database, Safir will attempt the initialization five times, two seconds apart, to allow time for networking or a database proxy to start.

To drop and recreate all of the tables, pass the ``reset=True`` option to `~safir.database.initialize_database`.

Note that `~safir.database.initialize_database` returns a `~sqlalchemy.ext.asyncio.AsyncEngine` object for the newly-initialized database.
This can be used to perform any further application-specific database initialization that is required, such as adding default table entries.
Put any such code before the ``await engine.dispose()`` call.

Using non-default PostgreSQL schemas
------------------------------------

Occasionally it's convenient for multiple applications to share the same database but use separate collections of tables.
PostgreSQL supports serving multiple schemas (in the sense of a namespace of tables) from the same database, and SQLAlchemy supports specifying the PostgreSQL schema for a given collection of tables.

The normal way to do this in SQLAlchemy is to modify the `~sqlalchemy.orm.DeclarativeBase` subclass used by the table definitions to specify a non-default schema.
For example:

.. code-block:: python

   from sqlalchemy import MetaData
   from sqlalchemy.orm import DeclarativeBase

   from ..config import config


   class Base(DeclarativeBase):
       metadata = MetaData(schema=config.database_schema)

If ``config.database_schema`` is `None`, the default schema will be used; otherwise, SQLAlchemy will use the specified schema instead of the default one.

Safir supports this in database initialization by creating a non-default schema if one is set.
If the ``schema`` attribute is set (via code like the above) on the SQLAlchemy metadata passed to the ``schema`` parameter of `~safir.database.initialize_database`, it will create that schema in the PostgreSQL database if it does not already exist.

Running database initialization on pod startup
----------------------------------------------

The recommended pattern for Safir-based applications that use a database is to initialize the database every time the pod has been restarted.
Since initialization does nothing if the schema already exists, this is safe to do.
It only wastes a bit of time during normal startup.
This allows the application to be deployed on a new cluster without any special initialization step.

The easiest way to do this is to add a script (conventionally located in ``scripts/start-frontend.sh``) that runs the ``init`` command and then starts the application with Uvicorn_:

.. code-block:: sh

   #!/bin/bash

   set -eu

   application init
   uvicorn application.main:app --host 0.0.0.0 --port 8080

Replace ``application`` with the application entry point (the first line) and Python module (the second line).
(These may be different if the application name contains dashes.)

Then, use this as the default command for the Docker image:

.. code-block:: docker

   COPY scripts/start-frontend.sh /start-frontend.sh
   CMD ["/start-frontend.sh"]

As a side effect, this will test database connectivity during pod startup and wait for network or a database proxy to be ready if needed, which avoids the need for testing database connectivity during the application startup.

.. _fastapi-database-session:

Using a database session in request handlers
============================================

For FastAPI applications, Safir provides a FastAPI dependency that creates a database session for each request.
This uses the `SQLAlchemy async_scoped_session <https://docs.sqlalchemy.org/en/14/orm/extensions/asyncio.html#using-asyncio-scoped-session>`__ to transparently manage a separate session per running task.

To use the database session dependency, it must first be initialized during application startup.
Generally this is done inside the application startup event:

.. code-block:: python

   from safir.dependencies.db_session import db_session_dependency

   from .config import config


   @app.on_event("startup")
   async def startup_event() -> None:
       await db_session_dependency.initialize(
           config.database_url, config.database_password
       )

As with some of the examples above, this assumes the application has a ``config`` object with the application settings, including the database URL and password.

You must also close the dependency during application shutdown:

.. code-block:: python

   @app.on_event("shutdown")
   async def shutdown_event() -> None:
       await db_session_dependency.aclose()

Then, any handler that needs a database session can depend on the `~safir.dependencies.db_session.db_session_dependency`:

.. code-block:: python

   from fastapi import Depends
   from safir.dependencies.db_session import db_session_dependency
   from sqlalchemy.ext.asyncio import async_scoped_session


   @app.get("/")
   async def get_index(
       session: async_scoped_session = Depends(db_session_dependency),
   ) -> Dict[str, str]:
       async with session.begin():
           # ... do something with session here ...
           return {}

Transaction management
----------------------

The application must manage transactions when using the Safir database dependency.
SQLAlchemy will automatically start a transaction if you perform any database operation using a session (including read-only operations).
If that transaction is not explicitly ended, `asyncpg`_ may leave it open, which will cause database deadlocks and other problems.

Generally it's best to manage the transaction in the handler function (see the ``get_index`` example, above).
Wrap all code that may make database calls in an ``async with session.begin()`` block.
This will open a transaction, commit the transaction at the end of the block, and roll back the transaction if the block raises an exception.

.. note::

   Due to an as-yet-unexplained interaction with FastAPI 0.74 and later, managing the transaction inside the database session dependency does not work.
   Calling ``await session.commit()`` there, either explicitly or implicitly via a context manager, immediately fails by raising ``asyncio.CancelledError`` and the transaction is not committed or closed.

.. _database-datetime:

Handling datetimes in database tables
=====================================

When a database column is defined using the SQLAlchemy ORM using the `~sqlalchemy.types.DateTime` generic type, it cannot store a timezone.
The SQL standard type `~sqlalchemy.types.DATETIME` may include a timezone with some database backends, but it is database-specific.
It is therefore normally easier to store times in the database in UTC without timezone information.

However, `~datetime.datetime` objects in regular Python code should always be timezone-aware and use the UTC timezone.
Timezone-naive datetime objects are often interpreted as being in the local timezone, whatever that happens to be.
Keeping all datetime objects as timezone-aware in the UTC timezone will minimize surprises from unexpected timezone conversions.

This unfortunately means that the code for storing and retrieving datetime objects from the database needs a conversion layer.
`asyncpg`_ wisely declines to convert datetime objects and therefore returns timezone-naive objects from the database and raises an exception if a timezone-aware datetime object is stored in a DateTime field.
The conversion must therefore be done in the code making SQLAlchemy calls.

Safir provides `~safir.database.datetime_to_db` and `~safir.database.datetime_from_db` helper functions to convert from a timezone-aware datetime to a timezone-naive datetime suitable for storing in a DateTime column, and vice versa.
These helper functions should be used wherever DateTime columns are read or updated.
`~safir.database.datetime_to_db` ensures the provided datetime object is timezone-aware and in UTC and converts it to a timezone-naive UTC datetime for database storage.
`~safir.database.datetime_from_db` ensures the provided datetime object is either timezone-naive or in UTC and returns a timezone-aware UTC datetime object.
Both raise `ValueError` if passed datetime objects in some other timezone.
`~safir.database.datetime_to_db` also raises `ValueError` if passed a timezone-naive datetime object.
Both return `None` if passed `None`.

Here is example of reading an object from the database that includes DateTime columns:

.. code-block:: python

   from safir.database import datetime_from_db


   stmt = select(SQLJob).where(SQLJob.id == job_id)
   result = (await session.execute(stmt)).scalar_one()
   job = Job(
       job_id=job.id,
       # ...
       creation_time=datetime_from_db(job.creation_time),
       start_time=datetime_from_db(job.start_time),
       end_time=datetime_from_db(job.end_time),
       destruction_time=datetime_from_db(job.destruction_time),
       # ...
   )

Here is an example of updating a DateTime field in the database:

.. code-block:: python

   from safir.database import datetime_to_db


   async with session.begin():
       stmt = select(SQLJob).where(SQLJob.id == job_id)
       job = (await session.execute(stmt)).scalar_one()
       job.destruction_time = datetime_to_db(destruction_time)

Testing applications that use a database
========================================

The Safir database layer only supports PostgreSQL at present.
While support for SQLite could be added, testing against the database that will be used for production is usually a better strategy, since some bugs (particularly around transaction management) are sensitive to the choice of backend.
The recommended strategy for testing applications that use a database is to start a real PostgreSQL server for the tests.

To do this, modify the ``init`` target in ``Makefile`` to install ``tox-docker`` at the same time ``tox`` is installed.
Then, add the following to ``tox.ini`` to define a database container:

.. code-block:: ini

   [docker:postgres]
   image = postgres:latest
   ports =
       5432:5432/tcp
   environment =
       POSTGRES_PASSWORD = INSECURE-PASSWORD
       POSTGRES_USER = safir
       POSTGRES_DB = safir
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

Add a dependency on this container to your ``py`` test environment (and any other tox environments that will run ``pytest``):

.. code-block:: ini

   [testenv:py]
   # ...
   docker =
       postgres

You may want to also add this to any ``run`` test environment you have defined so that a PostgreSQL container will be started for the local development environment.

Assuming that your application uses environment variables to configure the database URL and password (the recommended approach), set those environment variables in the ``py`` test environment (and any other relevant test environments, such as ``run``):

.. code-block:: ini

   [testenv:py]
   # ...
   setenv =
       APP_DATABASE_URL = postgresql://safir@127.0.0.1/safir
       APP_DATABASE_PASSWORD = INSECURE-PASSWORD

Change the names of the environment variables to match those used by your application, and change the database user and database name to match your application if you did so in the ``[docker:postgres]`` section.

Then, initialize the database in a test fixture.
The simplest way to do this is to add a call to `~safir.database.initialize_database` to the ``app`` fixture.
For example:

.. code-block:: python

   from collections.abc import AsyncIterator

   import pytest_asyncio
   from asgi_lifespan import LifespanManager
   from fastapi import FastAPI
   from safir.database import create_database_engine, initialize_database

   from application import main
   from application.config import config
   from application.schema import Base


   @pytest_asyncio.fixture
   async def app() -> AsyncIterator[FastAPI]:
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
   This in turn means that plugins like `pytest-xdist <https://pypi.org/project/pytest-xdist/>`__ unfortunately cannot be used to speed up tests.

Less-used database operations
=============================

Safir provides support for some other database operations that most applications will not need, but which are helpful in some complex use cases.

.. _async-db-session:

Creating an async database session
----------------------------------

.. note::

   This section describes how to get a database session outside of a FastAPI route handler, such as for cron jobs, background processing, or other non-web-application uses.
   Most applications will use database sessions in the context of a FastAPI handler and should instead use the corresponding FastAPI dependency instead of the code below.
   See :ref:`fastapi-database-session` for more details.

To get a new async database connection, use code like the following:

.. code-block:: python

   import structlog
   from safir.database import create_async_session, create_database_engine

   from .config import config


   engine = create_database_engine(
       config.database_url, config.database_password
   )
   session = await create_async_session(engine)

   # ... use the session here ...

   await session.remove()
   await engine.dispose()

Creating the engine is separate from creating the session so that the engine can be disposed of properly, which ensures the connection pool is closed.

.. _probing-db-connection:

Probing the database connection
-------------------------------

`~safir.database.create_async_session` supports probing the database to ensure that it is accessible and the schema is set up correctly.
To do this, pass a SQL statement to execute as the ``statement`` argument to `~safir.database.create_async_session`.
This will be called with ``.limit(1)`` to test the resulting session.
When ``statement`` is provided, a `structlog`_ logger must also be provided to log any errors when trying to run the statement.

For example:

.. code-block:: python

   import structlog
   from sqlalchemy.future import select

   from .schema import User


   logger = structlog.get_logger(config.logger_name)
   stmt = select(User)
   session = await create_async_session(engine, logger, statement=stmt)

If the statement fails, it will be retried up to five times, waiting two seconds between attempts, before raising the underlying exception.
This is particularly useful for waiting for network or a database proxy to come up when a process has first started.

Creating a sync database session
--------------------------------

Although Safir is primarily intended to support asyncio applications, it may sometimes be necessary to write sync code that performs database operations.
One example would be `Dramatiq <https://dramatiq.io/>`__ workers.
This can be done with `~safir.database.create_sync_session`.

.. code-block:: python

   from safir.database import create_sync_session

   from .config import config


   session = create_sync_session(config.database_url, config.database_password)
   with session.begin():
       # ... do something with the session ...
       pass

Unlike `~safir.database.create_async_session`, `~safir.database.create_sync_session` handles creating the engine internally, since sync engines do not require any special shutdown measures.

As with :ref:`async database sessions <probing-db-connection>`, you can pass a `structlog`_ logger and a statement to perform a connection check on the database before returning the session:

.. code-block:: python

   import structlog
   from safir.database import create_sync_session
   from sqlalchemy.future import select

   from .config import config
   from .schema import User


   logger = structlog.get_logger(config.logger_name)
   stmt = select(User)
   session = create_sync_session(
       config.database_url,
       config.database_password,
       logger,
       statement=stmt,
   )

Applications that use `~safir.database.create_sync_session` must declare a dependency on `psycopg2 <https://pypi.org/project/psycopg2/>`__ in their pip dependencies.
Safir itself does not depend on psycopg2, even with the ``db`` extra, since most applications that use Safir for database support will only need async sessions.

Setting an isolation level
--------------------------

`~safir.database.create_database_engine`, `~safir.database.create_sync_session`, and the ``initialize`` method of `~safir.dependencies.db_session.db_session_dependency` take an optional ``isolation_level`` argument that can be used to set a non-default isolation level.
If given, this parameter is passed through to the underlying SQLAlchemy engine.
See `the SQLAlchemy isolation level documentation <https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#setting-transaction-isolation-levels-dbapi-autocommit>`__ for more information.

You may have to set a custom isolation level, such as ``REPEATABLE READ``, if you have multiple simultaneous database writers and need to coordinate their writes to ensure consistent results.

Be aware that most situations in which you need to set a custom isolation level will also result in valid transactions raising exceptions indicating that they need to be retried, because another writer changed the database while the transaction was in progress.
You therefore will probably need to disable transaction management for the `~safir.dependencies.db_session.db_session_dependency` by passing ``manage_transactions=False`` to the ``initialize`` method and then manage transactions directly in the code (usually inside retry loops).
