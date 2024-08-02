.. currentmodule:: safir.uws

##########################
Creating a new UWS service
##########################

To create a new service that uses the Safir UWS library for its API, first create a new FastAPI Safir application.
The easiest way to do this is to follow the instructions in :ref:`create-from-template`.
Select the ``UWS`` flavor.

Then, flesh out the application by following these steps:

#. :doc:`Define the API parameters <define-inputs>`
#. :doc:`Define the parameter models <define-models>`
#. :doc:`Write the backend worker <write-backend>`
#. :doc:`Write the test suite <testing>`

If you use the template and select the ``UWS`` flavor, all of the steps below will be done for you and you can skip the rest of this page.
Read on if you're curious about what the ``UWS`` flavor sets up, or if you're converting an already-existing FastAPI application.

.. _uws-config:

Add UWS configuration options
=============================

UWS applications have several standard configuration options that you will want to include in your application's overall configuration.
You will also need to add a method to creete the `UWSConfig` object from your application configuration and to create a global `UWSApplication` object.
These need to be added to :file:`config.py`.

First, add additional configuration settings for UWS to ``Config`` by changing the class to inherit from `UWSAppSettings`.
This will add standard configuration options most services will need and provide helper methods and properties.

.. code-block:: python
   :caption: config.py

   from safir.uws import UWSAppSettings


   class Config(UWSAppSettings): ...

Second, add a property to ``Config`` that returns the UWS configuration.
For some of these settings, you won't know the values yet.
You will be able to fill in the value of ``parameters_type`` after reading :doc:`define-models`, the values of ``async_post_route`` and optionally ``sync_get_route`` and ``sync_post_route`` after reading :doc:`define-inputs`, and the value of ``worker`` after reading :doc:`write-backend`.
For now, you can just insert placeholder values.

.. code-block:: python
   :caption: config.py
   :emphasize-lines: 1,7-15

   from safir.uws import UWSAppSettings, UWSConfig, UWSRoute


   class Config(UWSAppSettings):
       ...

       @property
       def uws_config(self) -> UWSConfig:
           return self.build_uws_config(
               async_post_route=UWSRoute(...),
               parameters_type=...,
               sync_get_route=UWSRoute(...),
               sync_post_route=UWSRoute(...),
               worker=...,
           )

See `UWSAppSettings.build_uws_config` for all of the possible settings.

Third, at the bottom of :file:`config.py`, create the `UWSApplication` object and store it in ``uws``, which should be an exported symbol (listed in ``__all__``).

.. code-block:: python
   :caption: config.py
   :emphasize-lines: 1,8-9

   from safir.uws import UWSApplication

   ...

   config = Config()
   """Configuration for example."""

   uws = UWSApplication(config.uws_config)
   """The UWS application for this service."""

Set up the FastAPI application
==============================

The Safir UWS library must be initialized when the application starts, and requires some additional FastAPI middleware and error handlers.
These need to be added to :file:`main.py`.

First, initialize the UWS application in the ``lifespan`` function:

.. code-block:: python
   :caption: main.py
   :emphasize-lines: 1,6,8

   from .config import uws


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncIterator[None]:
       await uws.initialize_fastapi()
       yield
       await uws.shutdown_fastapi()
       await http_client_dependency.aclose()

Second, install the UWS routes into the external router before including it in the application:

.. code-block:: python
   :caption: main.py
   :emphasize-lines: 3

   # Attach the routers.
   app.include_router(internal_router)
   uws.install_handlers(external_router)
   app.include_router(external_router, prefix=f"{config.path_prefix}")

Third, install the UWS middleware and error handlers.

.. code-block:: python
   :caption: main.py
   :emphasize-lines: 3,5-6

   # Add middleware.
   app.add_middleware(XForwardedMiddleware)
   uws.install_middleware(app)

   # Install error handlers.
   uws.install_error_handlers(app)

Add a command-line interface
============================

The UWS implementation uses a PostgreSQL database to store job status.
Your application will need a mechanism to initialize that database with the desired schema.
The simplest way to do this is to add a command-line interface for your application with an ``init`` command that initializes the database.

.. note::

   This approach has inherent race conditions and cannot handle database schema upgrades.
   It will be replaced with a more sophisticated approach using Alembic_ once that support is ready.

First, create a new :file:`cli.py` file in your application with the following contents:

.. code-block:: python
   :caption: cli.py

   import click
   import structlog
   from safir.asyncio import run_with_asyncio
   from safir.click import display_help

   from .config import uws


   @click.group(context_settings={"help_option_names": ["-h", "--help"]})
   @click.version_option(message="%(version)s")
   def main() -> None:
       """Administrative command-line interface for example."""


   @main.command()
   @click.argument("topic", default=None, required=False, nargs=1)
   @click.pass_context
   def help(ctx: click.Context, topic: str | None) -> None:
       """Show help for any command."""
       display_help(main, ctx, topic)


   @main.command()
   @click.option(
       "--reset", is_flag=True, help="Delete all existing database data."
   )
   @run_with_asyncio
   async def init(*, reset: bool) -> None:
       """Initialize the database storage."""
       logger = structlog.get_logger("example")
       await uws.initialize_uws_database(logger, reset=reset)

Look for the instances of ``example`` and replace them with the name of your application.

Second, register this interface with Python in :file:`pyproject.toml`:

.. code-block:: toml
   :caption: pyproject.toml

   [project.scripts]
   example = "example.cli:main"

Again, replace ``example`` with the name of your application.

Third, change the :file:`Dockerfile` for your application to run a startup script rather than run :command:`uvicorn` directly:

.. code-block:: docker
   :caption: Dockerfile

   # Copy the startup script
   COPY scripts/start-frontend.sh /start-frontend.sh

   # Run the application.
   CMD ["/start-frontend.sh"]

Finally, create the :file:`scripts/start-frontend.sh` file:

.. code-block:: bash
   :caption: scripts/start-frontend.sh

   #!/bin/bash
   #
   # Create the database and then start the server.

   set -eu

   example init
   uvicorn example.main:app --host 0.0.0.0 --port 8080

Again, replace ``example`` with the name of your application.

Create the arq worker for database updates
==========================================

Your application will have two separate arq_ worker pods, one to do the actual work of your application and one to handle database updates and state tracking.
The code for the second worker is part of the UWS library, but you have to add a small amount of code to enable it and attach it to your application configuration.

Create a subdirectory named :file:`workers` in the source for your application with an empty :file:`workers/__init__.py` file.
Then, create :file:`workers/uws.py` with the following contents:

.. code-block:: python
   :caption: workers/uws.py

   import structlog
   from safir.logging import configure_logging

   from ..config import config, uws


   configure_logging(
       name="example", profile=config.profile, log_level=config.log_level
   )

   WorkerSettings = uws.build_worker(structlog.get_logger("example"))
   """arq configuration for the UWS database worker."""

Once again, replace ``example`` with the name of your application.

Next steps
==========

Now that you have set up the basic structure of your application, you can move on to the substantive parts.

- Define the API parameters: :doc:`define-inputs`
- Define the parameter models: :doc:`define-models`
- Write the backend worker :doc:`write-backend`
