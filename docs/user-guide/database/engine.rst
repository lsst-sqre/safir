:og:description: Learn how to manage the database engine.

.. py:currentmodule:: safir.database

############################
Managing the database engine
############################

SQLAlchemy maintains a connection pool for the database in an object called the database engine.
Normally, an application should create the SQLAlchemy engine during startup and clean it up on application exit.

Safir provides an async context manager to handle this.
In addition to managing the lifecycle of the database engine, it also cleans up any associated resources that must have the same lifespan as the engine, such as the Cloud SQL connection manager.

Engine manager arguments
========================

When using the Safir database support code, engines are always created with `engine_manager`.
The first argument is the database configuration, which must be either `DatabaseSettings` or `CloudSqlSettings`, as documented in :doc:`settings`.

There is an optional second argument, ``connect_args``, that if given provides additional parameters that are passed directly to the underlying database engine.
This can be used to configure lower-level settings such as SSL settings for the database.

.. _database-engine-fastapi:

FastAPI applications
====================

For FastAPI applications, the engine should be managed by the ``lifespan`` function passed into the FastAPI application constructor.
Here is a typical approach:

.. code-block:: python

   from collections.abc import AsyncGenerator
   from contextlib import asynccontextmanager

   import structlog
   from fastapi import FastAPI
   from safir.database import create_database_engine, is_database_current
   from safir.dependencies.db_session import db_session_dependency

   from .dependencies.config import config_dependency


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
       config = config_dependency.config()
       logger = structlog.get_logger("example")

       async with engine_manager(config.database) as engine:
           if not await is_database_current(engine, logger):
               raise RuntimeError("Database schema out of date")
           db_session_dependency.initialize_with_engine(engine)
           yield


   app = FastAPI(lifespan=lifespan)

If the database schema is out of date, the application will now refuse to start.
You may wish to define a custom exception for this problem rather than using `RuntimeError`.

If the application has any other entry points that use the database — other CLI commands, Kubernetes operators, or arq_ workers, for example — all of those entry points should include similar code to check the database schema before any operation that uses the database.

Click commands
==============

Within a Click command, the pattern is much simpler.
Use the `~safir.click.run_with_asyncio` decorator and wrap the code with the `engine_manager` async context manager.
For example:

.. code-block:: python

   from safir.click import run_with_asyncio
   from safir.database import engine_manager

   from example.dependencies.config import config_dependency


   @main.command()
   @run_with_asyncio
   async def some_command() -> None:
       config = await config_dependency()
       async with engine_manager(config.database) as engine:
           ...

arq and similar contexts
========================

For :doc:`arq workers </user-guide/arq>` and other situations, such as `Kopf Kubernetes operators <https://docs.kopf.dev/en/stable/>`__, that set up a context during process start and cannot easily use an async context manager, the engine can be created via a function call.
In this case, the caller is responsible for cleaning up the engine resources before process exit.

For code of this type, call `engine_manager` outside of an async context manager to create an engine manager object, and then use its `EngineManager.create_engine` and `EngineManager.aclose` methods.
The basic code flow should look like:

.. code-block::

   from typing import Any

   from safir.database import engine_manager

   from example.dependencies.config import config_dependency

   async def startup(ctx: dict[str, Any]) -> None:
       config = await config_dependency()
       manager = engine_manager(config.database)
       engine = await manager.create_engine()

       ctx["engine_manager"] = manager
       ctx["engine"] = engine

   async def shutdown(ctx: dict[str, Any]) -> None:
       manager = ctx["engine_manager"]
       await manager.aclose()

Other handlers or callbacks can then use the ``engine`` attribute of the context freely.
Change the names and signatures of the ``startup`` and ``shutdown`` methods for whatever framework you use.
