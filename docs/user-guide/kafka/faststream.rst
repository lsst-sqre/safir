##################
FastStream helpers
##################

FastStream will catch and log any uncaught exceptions in handler functions, but it will not re-raise them.
This means that they will not bubble up to any code that handles exceptions further up the callstack, like `Sentry`_.
Safir contains a `FastStream ExceptionMiddleware`_ that will report uncaught exceptions to Slack or Sentry or both depending on what you have configured in your app.

.. note::

   ``fastream.kafka.fastapi.KafkaRouter`` and ``fastream.kafka.fastapi.KafkaRouter`` provided by the `FastStream FastAPI plugin`_ each take a ``route_handler`` parameter.
   It may seem like we could get some of this error handling functionality by passing `~safir.slack.webhook.SlackRouteErrorHandler` to that parameter.
   This parameter doesn't have any effect on the Kafka handlers though, which is why we need a separate ``ExceptionMiddleware``.

Slack
=====
To configure your faststream app to report uncaught errors in handlers to Sentry:

* Add a `~safir.kafka.FastStreamErrorHandler` middleware to your router or broker ``middlewares`` with `~safir.kafka.FastStreamErrorHandler.make_middleware`
* Call `~safir.kafka.FastStreamErrorHandler.initialize_slack` with a valid Slack webhook URL

.. code-block:: python

   from safir.kafka import FastStreamErrorHandler

   from .config import config

   faststream_error_handler = FastStreamErrorHandler()

   kafka_router = KafkaRouter(
       middlewares=[faststream_error_handler.make_middleware()],
       **kafka_params,
       logger=logger,
   )

   logger = get_logger("my-app")

   if config.slack.enabled:
       faststream_error_handler.initialize_slack(
           config.slack.webhook, "my-app", logger
       )

Sentry
======

To configure your faststream app to report uncaught errors in handlers to Sentry:

* :ref:`instrument your app for Sentry <sentry-instrumentation>` as usual using the Safir sentry helpers
* Add the `~safir.kafka.FastStreamErrorHandler` to your router or broker ``middlewares``

If you follow the above instructions for configuring the ``FastStreamErrorHandler`` for Slack, you just need to add the ``initialize_sentry`` call below, and the ``FastStreamErrorHandler`` will also report errors to Sentry.

.. code-block:: python

   from safir.kafka import FastStreamErrorHandler
   from safir.sentry import initialize_sentry

   # If a Sentry DSN is provided in an environment variable, then
   # exceptions will be reported to Sentry.
   initialize_sentry()

   faststream_error_handler = FastStreamErrorHandler()

   kafka_router = KafkaRouter(
       middlewares=[faststream_error_handler.make_middleware()],
       **kafka_params,
       logger=logger,
   )
