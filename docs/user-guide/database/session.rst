.. py:currentmodule:: safir.database

###########################
Creating a database session
###########################

Most applications will use database sessions in the context of a FastAPI handler and should instead use the corresponding FastAPI dependency instead of the code below.
See :doc:`dependency` for more details.

This page describes how to get a database session outside of a FastAPI route handler, such as for cron jobs, background processing, or other non-web-application uses.

Basic session creation
======================

To get a new async database connection, use code like the following:

.. code-block:: python

   import structlog
   from safir.database import create_async_session, create_database_engine

   from .config import config

   engine = create_database_engine(
       config.database_url, config.database_password, pool_pre_ping=True
   )
   session = await create_async_session(engine)

   # ... use the session here ...

   await session.close()
   await engine.dispose()

Creating the engine is separate from creating the session so that the engine can be disposed of properly.
This ensures the connection pool is closed.

.. _db-engine-parameters:

Engine parameters
=================

The ``connect_args``, ``max_overflow``, ``pool_pre_ping``, ``pool_recycle``, ``pool_size``, and ``pool_timeout`` parameters to `create_database_engine` have the same meaning as the corresponding arguments to `sqlalchemy.create_engine`.

If the database client will only be interacting with the database intermittantly, consider setting ``pool_pre_ping=True`` in the parameters to `create_database_engine`.
This will verify that a connection is still open before reusing it for a session.
If it is not, a new connection will be opened without raising an exception that the caller has to catch.

See :doc:`retry` for more information about retrying database transaction failures.

If the connection idle timeout for the underlying database server is known, set ``pool_recycle`` to slightly less than that idle timeout in seconds.
SQLAlchemy will then refuse to reuse any connection that has been open for longer than that period and will instead create a new connection.

.. _probing-db-connection:

Probing the database connection
===============================

`create_async_session` supports probing the database to ensure that it is accessible and the schema is set up correctly.

To do this, pass a SQL statement to execute as the ``statement`` argument to `create_async_session`.
This will be called with ``.limit(1)`` to test the resulting session.
When ``statement`` is provided, a `structlog`_ logger must also be provided to log any errors when trying to run the statement.

For example:

.. code-block:: python

   import structlog
   from sqlalchemy import select

   from .schema import User

   logger = structlog.get_logger(config.logger_name)
   stmt = select(User)
   session = await create_async_session(engine, logger, statement=stmt)

If the statement fails, it will be retried up to five times, waiting two seconds between attempts, before raising the underlying exception.
This is particularly useful for waiting for network or a database proxy to come up when a process has first started.
