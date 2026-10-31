:og:description: Learn how to use the Safir database session FastAPI dependency.

.. py:currentmodule:: safir.dependencies.db_session

############################################
Using a database session in request handlers
############################################

For FastAPI applications, Safir provides a FastAPI dependency that creates a database session for each request.

Initialize the dependency
=========================

To use the database session dependency, it must first be initialized during application startup.
Generally this is done inside the application lifespan function inside the `~safir.database.engine_manager` async context manager.
See :ref:`database-engine-fastapi` for more details.

Using the dependency
====================

Any handler that needs a database session can then depend on `db_session_dependency`:

.. code-block:: python

   from typing import Annotated

   from fastapi import Depends
   from safir.dependencies.db_session import db_session_dependency
   from sqlalchemy.ext.asyncio import AsyncSession


   @app.get("/")
   async def get_index(
       session: Annotated[AsyncSession, Depends(db_session_dependency)],
   ) -> Dict[str, str]:
       async with session.begin():
           # ... do something with session here ...
           return {}

Transaction management
======================

The application must manage transactions when using the Safir database dependency.
SQLAlchemy will automatically start a transaction if you perform any database operation using a session (including read-only operations).
If that transaction is not explicitly ended, asyncpg_ may leave it open, which will cause database deadlocks and other problems.

Generally it's best to manage the transaction in either the handler function (see the ``get_index`` example, above) or the service layer.
Wrap all code that may make database calls in an ``async with session.begin()`` block.
This will open a transaction, commit the transaction at the end of the block, and roll back the transaction if the block raises an exception.

.. note::

   Due to an as-yet-unexplained interaction with FastAPI 0.74 and later, managing the transaction inside the database session dependency does not work.
   Calling ``await session.commit()`` there, either explicitly or implicitly via a context manager, immediately fails by raising ``asyncio.CancelledError`` and the transaction is not committed or closed.
