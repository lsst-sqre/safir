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

Including uvicorn logs
----------------------

Uvicorn_ is normally used to run FastAPI web applications.
It logs messages about its own operations, and logs each request to the underlying web application.
By default, those logs use a separate logging profile and do not honor structlog configuration settings such as whether to log messages in JSON.

For consistency, you may want to route Uvicorn log messages through structlog.
Safir provides the `safir.logging.configure_uvicorn_logging` function to modify the Uvicorn logging configuration to do so:

.. code-block:: python

   configure_uvicorn_logging(config.log_level)

This should be called after `~safir.logging.configure_logging`.
To ensure that logging is reconfigured before Uvicorn logs its first message, it should be called either during import time of the module that provides the FastAPI application or during execution of a callable that constructs the FastAPI application

When `~safir.logging.configure_uvicorn_logging` is called, it will also add a log processor that parses the Uvicorn access log messages and adds structlog context in the format expected by Google's Cloud Logging system.

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

``httpRequest``
    A nested dictionary of information about the incoming request.
    This follows the format that Google's Cloud Logging system expects.
    It has the following keys:

    ``requestMethod``
        The HTTP method (such as GET, POST, DELETE).

    ``requestUrl``
        The requested URL.

    ``remoteIp``
        The IP address of the client.
        Use :ref:`XForwardedMiddleware <x-forwarded>` to log more accurate information for applications behind a Kubernetes ingress.

    ``userAgent``
        The ``User-Agent`` header of the HTTP request, if present.

``request_id``
    The request ID is a UUID.
    Use it to collect all messages generated from a given request.

The log message will look something like:

.. code-block:: json

   {
     "event": "My message",
     "httpRequest": {
       "requestMethod": "GET",
       "requestUrl": "https://example.com/exampleapp",
       "remoteIp": "192.168.1.1",
       "userAgent": "some-user-agent/1.0"
     },
     "logger": "myapp",
     "request_id": "d8fc02cf-40ac-4d35-bb59-1f0dd9ddedf6",
     "severity": "info",
     "somekey": 42,
   }

Authenticated routes
--------------------

If the route is protected by `Gafaelfawr`_, instead use ``auth_logger_dependency`` imported from ``safir.dependencies.gafaelfawr``.
This will behave the same except that it will bind the additional context field ``user`` to the authenticated user as asserted by the headers added by Gafaelfawr.

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
     "httpRequest": {
       "requestMethod": "GET",
       "requestUrl": "https://example.com/exampleapp",
       "remoteIp": "192.168.1.1",
       "userAgent": "some-user-agent/1.0"
     },
     "logger": "myapp",
     "request_id": "d8fc02cf-40ac-4d35-bb59-1f0dd9ddedf6",
     "severity": "info",
   }

.. code-block:: json

   {
     "answer": 42,
     "event": "Message 2",
     "httpRequest": {
       "requestMethod": "GET",
       "requestUrl": "https://example.com/exampleapp",
       "remoteIp": "192.168.1.1",
       "userAgent": "some-user-agent/1.0"
     },
     "logger": "myapp",
     "request_id": "d8fc02cf-40ac-4d35-bb59-1f0dd9ddedf6",
     "severity": "info",
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
