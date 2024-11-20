######################
Using the database API
######################

Safir-based applications that use a SQL database can use Safir to initialize that database and acquire a database session.
Safir-based applications that use FastAPI can also use the Safir-provided FastAPI dependency to manage per-request database sessions.
The Safir database support is based on `SQLAlchemy`_ and assumes use of PostgreSQL (possibly via `Cloud SQL <https://cloud.google.com/sql>`__) as the underlying database.

Safir is an asyncio framework and requires using SQLAlchemy's asyncio API.
Safir uses the `asyncpg`_ PostgreSQL database driver.

Database support in Safir is optional.
To use it, depend on ``safir[db]`` in your pip requirements.

Also see :ref:`pydantic-dsns` for Pydantic types that help with configuring the PostgreSQL DSN.

Guides
======

.. toctree::
   :titlesonly:

   initialize
   dependency
   session
   datetime
   retry
   pagination
   testing
   schema
