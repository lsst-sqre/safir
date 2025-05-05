############################################
Using a database session in request handlers
############################################

For FastAPI applications, Safir provides a FastAPI dependency that creates a database session for each request.
This uses the `SQLAlchemy async_scoped_session <https://docs.sqlalchemy.org/en/14/orm/extensions/asyncio.html#using-asyncio-scoped-session>`__ to transparently manage a separate session per running task.

Initialize the dependency
=========================

To use the database session dependency, it must first be initialized during application startup.
Generally this is done inside the application lifespan function.
You must also close the dependency during application shutdown.

.. code-block:: python

   from collections.abc import AsyncGenerator
   from contextlib import asynccontextmanager

   from fastapi import FastAPI
   from safir.dependencies.db_session import db_session_dependency

   from .config import config


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
       await db_session_dependency.initialize(
           config.database_url, config.database_password
       )
       yield
       await db_session_dependency.aclose()


   app = FastAPI(lifespan=lifespan)

`~safir.dependencies.db_session.DatabaseSessionDependency.initialize` takes the same optional parameters as `~safir.database.create_database_engine`.

As with some of the examples above, this assumes the application has a ``config`` object with the application settings, including the database URL and password.

Using the dependency
====================

Any handler that needs a database session can depend on the `~safir.dependencies.db_session.db_session_dependency`:

.. code-block:: python

   from typing import Annotated

   from fastapi import Depends
   from safir.dependencies.db_session import db_session_dependency
   from sqlalchemy.ext.asyncio import async_scoped_session


   @app.get("/")
   async def get_index(
       session: Annotated[
           async_scoped_session, Depends(db_session_dependency)
       ],
   ) -> Dict[str, str]:
       async with session.begin():
           # ... do something with session here ...
           return {}

Transaction management
======================

The application must manage transactions when using the Safir database dependency.
SQLAlchemy will automatically start a transaction if you perform any database operation using a session (including read-only operations).
If that transaction is not explicitly ended, `asyncpg`_ may leave it open, which will cause database deadlocks and other problems.

Generally it's best to manage the transaction in the handler function (see the ``get_index`` example, above).
Wrap all code that may make database calls in an ``async with session.begin()`` block.
This will open a transaction, commit the transaction at the end of the block, and roll back the transaction if the block raises an exception.

.. note::

   Due to an as-yet-unexplained interaction with FastAPI 0.74 and later, managing the transaction inside the database session dependency does not work.
   Calling ``await session.commit()`` there, either explicitly or implicitly via a context manager, immediately fails by raising ``asyncio.CancelledError`` and the transaction is not committed or closed.
