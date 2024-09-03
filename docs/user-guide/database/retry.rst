##############################
Retrying database transactions
##############################

To aid in retrying transactions, Safir provides a decorator function, `safir.database.retry_async_transaction`.
Retrying transactions is often useful in conjunction with a custom transaction isolation level.

Setting an isolation level
==========================

If you have multiple simultaneous database writers and need to coordinate their writes to ensure consistent results, you may have to set a custom isolation level, such as ``REPEATABLE READ``,
In this case, transactions that attempt to modify an object that was modified by a different connection will raise an exception and can be retried.

`~safir.database.create_database_engine` and the ``initialize`` method of `~safir.dependencies.db_session.db_session_dependency` take an optional ``isolation_level`` argument that can be used to set a non-default isolation level.
If given, this parameter is passed through to the underlying SQLAlchemy engine.

See `the SQLAlchemy isolation level documentation <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#setting-transaction-isolation-levels-dbapi-autocommit>`__ for more information.
See :doc:`dependency` and :doc:`session` for more information about initializing the database engine.

Retrying transactions
=====================

To retry failed transactions in a function or method, decorate that function or method with `~safir.database.retry_async_transaction`.

If the decorated function or method raises `sqlalchemy.exc.DBAPIError` (the parent exception for exceptions raised by the underlying database API), it will be re-ran with the same arguments.
This will be repeated a configurable number of times (three by default).
The decorated function or method must therefore be idempotent and safe to run repeatedly.

Here's a simplified example from the storage layer of a Safir application:

.. code-block:: python

   from datetime import datetime

   from safir.database import datetime_to_db, retry_async_transaction
   from sqlalchemy.ext.asyncio import async_scoped_session


   class Storage:
       def __init__(self, session: async_scoped_session) -> None:
           self._session = session

       @retry_async_transaction
       async def mark_start(self, job_id: str, start: datetime) -> None:
           async with self._session.begin():
               job = await self._get_job(job_id)
               if job.phase in ("PENDING", "QUEUED"):
                   job.phase = "EXECUTING"
               job.start_time = start

If this method races with other methods updating the same job, the custom isolation level will force this update to fail with an exception, and it will then be retried by the decorator.

Changing the retry delay
------------------------

The decorator will delay for half a second (configurable with the ``delay`` parameter) between attempts, and by default the method is attempted three times.
These can be changed with a parameter to the decorator, such as:

.. code-block:: python
   :emphasize-lines: 2

   class Storage:
       @retry_async_transaction(max_tries=5, delay=2.5)
       async def mark_start(self, job_id: str, start: datetime) -> None:
           async with self._session.begin():
               ...
