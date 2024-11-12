#####################################
Handling datetimes in database tables
#####################################

When a database column is defined using the SQLAlchemy ORM using the `~sqlalchemy.types.DateTime` generic type, it cannot store a timezone.
The SQL standard type `~sqlalchemy.types.DATETIME` may include a timezone with some database backends, but it is database-specific.
For PostgreSQL, if the column is timezone-aware, PostgreSQL will convert the time to what it believes to be the local timezone rather than leaving it in UTC.

It is therefore less error-prone to set a strict standard that all times must be stored in the database in UTC without timezone information.
This ensures the database always returns times in UTC.

However, `~datetime.datetime` objects in regular Python code should always be timezone-aware and use the UTC timezone.
Timezone-naive datetime objects are often interpreted as being in the local timezone, whatever that happens to be.
Keeping all datetime objects as timezone-aware in the UTC timezone will minimize surprises from unexpected timezone conversions.

This unfortunately means that the code for storing and retrieving datetime objects from the database needs a conversion layer.

Converting datetimes
====================

asyncpg_ wisely declines to convert datetime objects.
It therefore returns timezone-naive objects from the database, and raises an exception if a timezone-aware datetime object is stored in a `~sqlalchemy.types.DateTime` field.
The conversion must therefore be done in the code making SQLAlchemy calls.

Safir provides `~safir.database.datetime_to_db` and `~safir.database.datetime_from_db` helper functions to convert from a timezone-aware datetime to a timezone-naive datetime suitable for storing in a DateTime column, and vice versa.
These helper functions should be used wherever `~sqlalchemy.types.DateTime` columns are read or updated.

`~safir.database.datetime_to_db` ensures the provided datetime object is timezone-aware and in UTC and converts it to a timezone-naive UTC datetime for database storage.
It raises `ValueError` if passed a timezone-naive datetime object.

`~safir.database.datetime_from_db` ensures the provided datetime object is either timezone-naive or in UTC and returns a timezone-aware UTC datetime object.

Both raise `ValueError` if passed datetime objects in some other timezone.
Both return `None` if passed `None`.

Examples
========

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
