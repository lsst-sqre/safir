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

Safir supports simple initialization of an empty database with a schema provided by the application.
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

Then, Safir can be used to initialize the database with code like:

.. code-block:: python

   import structlog
   from safir.database import initialize_database

   from .config import config
   from .schema import Base


   logger = structlog.get_logger(config.logger_name)
   engine = await initialize_database(
       config.database_url,
       config.database_password,
       logger,
       schema=Base.metadata,
   )
   await engine.dispose()

(Although not shown here, this must be done inside an ``async`` function.)
This code assumes that ``.config`` provides a ``config`` object that contains the settings for the application, including the database URL and password as well as the normal Safir configuration settings.

If it receives a connection error from the database, Safir will attempt the initialization five times, two seconds apart, to allow time for networking or a database proxy to start.

To drop and recreate all of the tables, pass the ``reset=True`` option to `~safir.database.initialize_database`.

Note that `~safir.database.initialize_database` returns a `~sqlalchemy.ext.asyncio.AsyncEngine` object for the newly-initialized database.
This can be used to perform any further application-specific database initialization that is required, such as adding default table entries.
Put any such code before the ``await engine.dispose()`` call.

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
       # ... do something with session here ...
       return {}

By default, the session returned by this dependency will be inside a transaction that will automatically be committed when the route handler returns.
This is normally the best way to write database code for a RESTful web application, since each request should be a single transaction.
However, be aware that this means you should call ``await session.flush()`` and not ``await session.commit()`` to make changes visible to subsequent database statements.

If you need to manage the transactions directly, disable automatic transaction management by passing ``manage_transactions=False`` to ``initialize`` during application startup.
The session returned by the dependency will then not have an open transaction, and you should put any database code inside an ``async with session.begin()`` block to create and commit a transaction.

.. _async-db-session:

Creating an async database session
==================================

.. note::

   This section describes how to get a database session outside of a FastAPI route handler, such as for cron jobs, background processing, or other non-web-application uses.
   Most applications will use database sessions in the context of a FastAPI handler and should instead use the corresponding FastAPI dependency instead of the code below.
   See :ref:`fastapi-database-session` for more details.

To get a new async database connection, use code like the following:

.. code-block:: python

   import structlog
   from safir.database import create_async_session, create_database_engine

   from .config import config


   engine = create_database_engine(config.database_url, config.database_password)
   session = await create_async_session(engine)

   # ... use the session here ...

   await session.remove()
   await engine.dispose()

Creating the engine is separate from creating the session so that the engine can be disposed of properly, which ensures the connection pool is closed.

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
================================

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

As with :ref:`async database sessions <async-db-session>`, you can pass a `structlog`_ logger and a statement to perform a connection check on the database before returning the session:

.. code-block:: python

   import structlog
   from safir.database import create_sync_session
   from sqlalchemy.future import select

   from .config import config
   from .schema import User


   logger = structlog.get_logger(config.logger_name)
   stmt = select(User)
   session = create_sync_session(
       config.database_url, config.database_password, logger, statement=stmt
   )

Applications that use `~safir.database.create_sync_session` must declare a dependency on `psycopg2 <https://pypi.org/project/psycopg2/>`__ in their pip dependencies.
Safir itself does not depend on psycopg2, even with the ``db`` extra, since most applications that use Safir for database support will only need async sessions.

Setting an isolation level
==========================

`~safir.database.create_database_engine`, `~safir.database.create_sync_session`, and the ``initialize`` method of `~safir.dependencies.db_sesssion.db_sesssion_dependency` take an optional ``isolation_level`` argument that can be used to set a non-default isolation level.
If given, this parameter is passed through to the underlying SQLAlchemy engine.
See `the SQLAlchemy isolation level documentation <https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#setting-transaction-isolation-levels-dbapi-autocommit>`__ for more information.

You may have to set a custom isolation level, such as ``REPEATABLE READ``, if you have multiple simultaneous database writers and need to coordinate their writes to ensure consistent results.

Be aware that most situations in which you need to set a custom isolation level will also result in valid transactions raising exceptions indicating that they need to be retried, because another writer changed the database while the transaction was in progress.
You therefore will probably need to disable transaction management for the `~safir.dependencies.db_sesssion.db_sesssion_dependency` by passing ``manage_transactions=False`` to the ``initialize`` method and then manage transactions directly in the code (usually inside retry loops).
