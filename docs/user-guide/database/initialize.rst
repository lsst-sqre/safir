#######################
Initializing a database
#######################

Safir supports simple initialization of a database with a schema provided by the application.
By default, this only adds any declared but missing tables, indices, or other objects, and thus does nothing if the database is already initialized.
The application may also request a database reset, which will drop and recreate all of the tables in the current schema.

More complex database schema upgrades are not supported by Safir.
If those are required, consider using `Alembic <https://alembic.sqlalchemy.org/en/latest/>`__.

Define the database schema
==========================

Database initialization in Safir assumes that the application has defined the database schema via the SQLAlchemy ORM.
The recommended way to do this is to add a ``schema`` directory to the application containing the table definitions.

In the file :file:`schema/base.py`, define the SQLAlchemy declarative base:

.. code-block:: python

   from sqlalchemy.orm import DeclarativeBase


   class Base(DeclarativeBase):
       """Declarative base for SQLAlchemy ORM model of database schema."""

In other files in that directory, define the database tables using the `normal SQLAlchemy ORM syntax <https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html#declarative-mapping>`__, one table per file.
Each database table definition must inherit from ``Base``, imported from ``.base``.

In :file:`schema/__init__.py`, import the table definitions from all of the files in the directory, as well as the ``Base`` class, and export them using ``__all__``.

Using non-default PostgreSQL schemas
------------------------------------

Sometimes it is convenient for multiple applications to share the same database but use separate collections of tables.
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

.. _database-init-cli:

Add a CLI command to initialize the database
============================================

The recommended approach to add database initialization to an application is to add an ``init`` command to the command-line interface that runs the database initialization code.
For applications using Click_ (the recommended way to implement a command-line interface), this can be done with code like:

.. code-block:: python

   import asyncio
   import click
   import structlog
   from safir.database import create_database_engine, initialize_database

   from .config import config
   from .schema import Base


   # Definition of main omitted.


   @main.command()
   @click.option(
       "--reset", is_flag=True, help="Delete all existing database data."
   )
   def init(*, reset: bool) -> None:
       logger = structlog.get_logger(config.logger_name)
       engine = create_database_engine(
           config.database_url, config.database_password
       )

       async def _init_db() -> None:
           await initialize_database(
               engine, logger, schema=Base.metadata, reset=reset
           )
           await engine.dispose()

       asyncio.run(_init_db())

This code assumes that ``main`` is the Click entry point and ``.config`` provides a ``config`` object that contains the settings for the application, including the database URL and password as well as the normal Safir configuration settings.
It uses an async helper function to initialize the database since this makes integration with Alembic management easier.
See :ref:`database-alembic-init` for more details.

The database URL may be a Pydantic ``Url`` type or a `str`.
The database password may be a ``pydantic.SecretStr``, a `str`, or `None` if no password is required by the database.

If it receives a connection error from the database, Safir will attempt the initialization five times, two seconds apart, to allow time for networking or a database proxy to start.

To drop and recreate all of the tables, pass the ``reset=True`` option to `~safir.database.initialize_database`.

Run database initialization on pod startup
==========================================

The recommended pattern for Safir-based applications that use a database but do not use Alembic is to initialize the database every time the pod has been restarted.

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
