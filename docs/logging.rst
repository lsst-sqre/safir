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

   config = Configuration()
   configure_logging(
       profile=config.profile,
       log_level=config.log_level,
       name=config.logger_name,
   )

.. note::

   The ``Configuration`` object is the responsibility of each each app to create.

   See the `~safir.logging.configure_logging` for details about the parameters.

.. _logging-in-handlers:

Logging in request handlers
===========================

Basic usage
-----------

Each handler that wants to use the logger requests it as a FastAPI dependency.

.. code-block:: python

   from structlog.stdlib import BoundLogger

   from safir.dependencies.logger import logger_dependency


   @app.get("/")
   async def get_index(
       logger: BoundLogger = Depends(logger_dependency),
   ) -> Dict[str, str]:
       logger.info("My message", somekey=42)
       return {}

This dependency creates a request-specific logger for each request with bound context fields:

``method``
    The HTTP method (such as GET, POST, DELETE).

``path``
    The path of the request.

``remote``
    The IP address of the client that sent the request.

``request_id``
    The request ID is a UUID.
    Use it to collect all messages generated from a given request.

``user_agent``
    The value of the ``User-Agent`` header, which can assist with debugging.

The log message will look something like:

.. code-block:: json

   {
     "event": "My message",
     "level": "info",
     "logger": "myapp",
     "method": "GET",
     "path": "/exampleapp/",
     "remote": "192.168.1.1",
     "request_id": "62983174-5c51-46ad-b451-d774562783b9",
     "somekey": 42,
     "user_agent": "some-user-agent/1.0"
   }

Binding extra context to the logger
-----------------------------------

You might wish to bind additional context to the request logger.
That way, each subsequent log message will include that context.
To bind new context, get a new logger with the `~structlog.BoundLogger.bind` method:

.. code-block:: python

   @routes.get("/")
   async def get_index(
       logger: BoundLogger = Depends(logger_dependency),
   ) -> Dict[str, str]:
       logger = logger.bind(answer=42)

       logger.info("Message 1")
       logger.info("Message 2")

       return web.json_response({})

This generates log messages:

.. code-block:: json

   {
     "answer": 42,
     "event": "Message 1",
     "level": "info",
     "logger": "myapp",
     "method": "GET",
     "path": "/exampleapp/",
     "remote": "192.168.1.1",
     "request_id": "62983174-5c51-46ad-b451-d774562783b9",
     "user_agent": "some-user-agent/1.0"
   }

.. code-block:: json

   {
     "answer": 42,
     "event": "Message 2",
     "level": "info",
     "logger": "myapp",
     "method": "GET",
     "path": "/exampleapp/",
     "remote": "192.168.1.1",
     "request_id": "62983174-5c51-46ad-b451-d774562783b9",
     "user_agent": "some-user-agent/1.0"
   }

Because `~structlog.BoundLogger.bind` returns a new logger, you'll need to pass this logger to any functions that your handler calls.

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
