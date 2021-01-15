#############################
Logging in Safir applications
#############################

Safir supports logging with structlog_, a structured logging library.
Rather than logging free-form messages, structured logging lets you create messages with easily parseable data attributes.

How to set up logging for Safir-based applications
==================================================

Safir configures structlog on two levels:

1. Configures logging in general.
2. Creates a logger for each request handler that binds context about the request.

**If you created your application following the template, these configurations are already in place.**
Skip to the sections :ref:`logging-in-handlers` and :ref:`logging-elsewhere`.

Configuring the logger
----------------------

To configure logging, run the `safir.logging.configure_logging` function in application set up:

.. code-block:: python

   def create_app() -> web.Application:
       config = Configuration()
       configure_logging(
           profile=config.profile,
           log_level=config.log_level,
           name=config.logger_name,
       )

       root_app = web.Application()

       return root_app

.. note::

   The ``Configuration`` object is the responsibility of each each app to create.

   See the `~safir.logging.configure_logging` for details about the parameters.

Configuring the logging middleware
----------------------------------

To enable the logging middleware for request handlers, append `safir.middleware.bind_logger` to `aiohttp.web.Application.middlewares`:

.. code-block:: python

   def create_app() -> web.Application:
       root_app = web.Application()
       root_app["safir/config"] = Configuration()
       app.middlewares.append(bind_logger)

       return app

.. important::

   `~safir.middleware.bind_logger` relies upon your application having a configuration object stored in your application under the ``safir/config`` key.
   This configuration object **must** have a ``logger_name`` attribute that matches the ``name`` parameter passed to `~safir.logging.configure_logging` in the first step.

This middleware creates a request-specific logger for each request with bound context fields:

``method``
    The HTTP method (such as GET, POST, DELETE).

``path``
    The path of the request.

``request_id``
    The request ID is a UUID.
    Use it to collect all messages generated from a given request.

For example, a JSON formatted log message from a request looks like this:

.. code-block:: json

   {
     "event": "Hello world",
     "method": "GET",
     "path": "/exampleapp/",
     "request_id": "62983174-5c51-46ad-b451-d774562783b9"
   }

.. _logging-in-handlers:

Logging in request handlers
===========================

Basic usage
-----------

Inside a request handler, get the logging from the ``"safir/logger"`` key of the request:

.. code-block:: python

   @routes.get("/")
   async def get_index(request: web.Request) -> web.Response:
       """GET /<path>/ (the app's external root)."""
       logger = request["safir/logger"]
       logger.info("My message", somekey=42)

       return web.json_response({})

The log message is:

.. code-block:: json

   {
     "event": "My message",
     "method": "GET",
     "path": "/exampleapp/",
     "request_id": "62983174-5c51-46ad-b451-d774562783b9",
     "somekey": 42
   }

Binding extra context to the logger
-----------------------------------

You might wish to bind additional context to the request logger.
That way, each subsequent log message will include that context.
To bind new context, get a new logger with the `~structlog.Boundlogger.bind` method:

.. code-block:: python

   @routes.get("/")
   async def get_index(request: web.Request) -> web.Response:
       logger = request["safir/logger"]
       logger = logger.bind(answer=42)

       logger.info("Message 1")
       logger.info("Message 2")

       return web.json_response({})

This generates log messages:

.. code-block:: json

   {
     "answer": 42,
     "event": "Message 1",
     "method": "GET",
     "path": "/exampleapp/",
     "request_id": "62983174-5c51-46ad-b451-d774562783b9"
   }

.. code-block:: json

   {
     "answer": 42,
     "event": "Message 2",
     "method": "GET",
     "path": "/exampleapp/",
     "request_id": "62983174-5c51-46ad-b451-d774562783b9"
   }

Because `~structlog.Boundlogger.bind` returns a new logger, you'll need to pass this logger to any functions that your handler calls.

.. _logging-elsewhere:

Logging elsewhere in your application
=====================================

You can use the logger in your application outside of HTTP request handlers.
For example, you can log during application set up, or as part of Kafka event handlers.

In that case, you can obtain the logger directly with `structlog.get_logger`:

.. code-block:: python

   import structlog

   logger = structlog.get_logger(__name__)
   logger.info("Hello world")

.. note::

   Using ``__name__`` as the logger name works because, as configured by the template, the logger name used by `safir.logging.configure_logging` is typically the application's package name.

   ``__name__`` is always either the package name itself, or within the namespace of the package, so you still get the same logger configuration as if you directly obtained the package's root logger:

   .. code-block:: python

      import structlog

      logger = structlog.get_logger("packagename")
      logger.info("Hello world")

   In many cases, you may *want* to explicitly use the application's root logger if you don't want your log messages to include the full namespace where each log message originated.
