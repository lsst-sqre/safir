:og:description: Learn how to use Safir's database support code.

######################
Using the database API
######################

Safir-based applications that use a SQL database can use Safir to initialize that database and acquire a database session.
Safir-based applications that use FastAPI can also use the Safir-provided FastAPI dependency to manage per-request database sessions.

The Safir database support is based on SQLAlchemy_ and has built-in support for `Cloud SQL <https://cloud.google.com/sql>`__.
Schema management is done with Alembic_.

Safir is an asyncio framework and requires using SQLAlchemy's asyncio API.
Safir uses the asyncpg_ PostgreSQL database driver by default for PostgreSQL databases and the asyncmy_ MySQL database driver by default for MySQL databases.
PostgreSQL is strongly preferred and should be used where possible.
Database engines other than PostgreSQL and MySQL/MariaDB have not been tested.

Database support in Safir is optional.
To use it, depend on ``safir[db]``.
When using Safir with a MySQL-compatible database, you will also need to depend on ``asyncmy``.

Guides
======

.. toctree::
   :titlesonly:

   settings
   schema
   engine
   dependency
   datetime
   retry
   pagination
   testing
