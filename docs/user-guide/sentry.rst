##################
Integrating Sentry
##################

`Sentry`_ is an exception reporting and tracing observability service.
It has great out-of-the-box integrations with many of the Python libaries that we use, including `FastAPI`_, `SQLAlchemy`_, and `arq`_.
Most apps can get a lot of value out of Sentry by doing nothing other than calling the `init function <https://docs.sentry.io/platforms/python/#configure>`_ early in their app and using some of the helpers described here.

Instrumenting your application
==============================

The simplest instrumentation involves calling ``sentry_sdk.init`` as early as possible in your app's ``main.py`` file.
You will need to provide at least:

* A Sentry DSN associated with your app's Sentry project
* An environment name with which to tag Sentry events

You can optionally provide:

* The `~safir.sentry.before_send_handler` `before_send`_ handler, which adds the environment to the Sentry fingerprint, and handles :ref:`sentry-exception-types` appropriately.
* A value to configure the `traces_sample_rate`_ so you can easily enable or disable tracing from Phalanx without changing your app's code
* Other `configuration options`_.

The ``sentry_sdk`` will automatically get the DSN and environment from the ``SENTRY_DSN`` and ``SENTRY_ENVIRONMENT`` environment vars, but you can also provide them explicitly via your app's config.
Unless you want to explicitly instrument app config initialization, you should probably provide these values with the rest of your app's config to keep all config in the same place.

Your config file may look something like this:

.. code-block:: python
   :caption: src/myapp/config.py

   class Configuration(BaseSettings):
       environment_name: Annotated[
           str,
           Field(
               alias="MYAPP_ENVIRONMENT_NAME",
               description=(
                   "The Phalanx name of the Rubin Science Platform environment."
               ),
           ),
       ]

       sentry_dsn: Annotated[
           str | None,
           Field(
               alias="MYAPP_SENTRY_DSN",
               description="DSN for sending events to Sentry.",
           ),
       ] = None

       sentry_traces_sample_rate: Annotated[
           float,
           Field(
               alias="MYAPP_SENTRY_TRACES_SAMPLE_RATE",
               description=(
                   "The percentage of transactions to send to Sentry, expressed "
                   "as a float between 0 and 1. 0 means send no traces, 1 means "
                   "send every trace."
               ),
               ge=0,
               le=1,
           ),
       ] = 0


   config = Configuration()

And your ``main.py`` might look like this:

.. code-block:: python
   :caption: src/myapp/main.py

   import sentry_sdk

   from safir.sentry import before_send_handler
   from .config import config


   sentry_sdk.init(
       dsn=config.sentry_dsn,
       environment=config.sentry_environment,
       traces_sample_rate=config.sentry_traces_sample_rate,
       before_send=before_send_handler,
   )


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncIterator: ...


   app = FastAPI(title="My App", lifespan=lifespan, ...)

.. _before_send: https://docs.sentry.io/platforms/python/configuration/options/#before-send
.. _traces_sample_rate: https://docs.sentry.io/platforms/python/configuration/options/#traces-sample-rate
.. _configuration options: https://docs.sentry.io/platforms/python/configuration/options/

.. _sentry-exception-types:

Special Sentry exception types
==============================

Similar to :ref:`slack-exceptions`, you can use `~safir.sentry.SentryException` to create custom exceptions that will send specific Sentry tags and contexts with any events that arise from them.
You need to use the `~safir.sentry.before_send_handler` handler for this to work.

SentryException
---------------

You can define custom exceptions that inherit from `~safir.sentry.SentryException`.
These exceptions will have ``tags`` and ``contexts`` attributes.
If Sentry sends an event that arises from reporting one of these exceptions, the event will have those tags and contexts attached to it.

.. note::

   `Tags <https://docs.sentry.io/platforms/python/enriching-events/tags/>`_ are short key-value pairs that are indexed by Sentry. Use tags for small values that you would like to search by and aggregate over when analyzing multiple Sentry events in the Sentry UI.
   `Contexts <https://docs.sentry.io/platforms/python/enriching-events/context/>`_ are for more detailed information related to single events. You can not search by context values, but you can store more data in them.
   You should use a tag for something like ``"query_type": "sync"`` and a context for something like ``"query_info": {"query_text": text}``

.. code-block:: python

   from safir.sentry import sentry_exception_handler, SentryException


   sentry_sdk.init(before_send=sentry_exception_handler)


   class SomeError(SentryException):
       def __init__(
           self, message: str, some_tag: str, some_context: dict[str, Any]
       ) -> None:
           super.__init__(message)
           self.tags["some_tag"] = some_tag
           self.contexts["some_context"] = some_context


   raise SomeError(
       "Some error!", some_tag="some_value", some_context={"foo": "bar"}
   )

SentryWebException
------------------

Similar to :ref:`slack-web-exceptions`, you can use `~safir.sentry.SentryWebException` to report an `HTTPX`_ exception with helpful info in tags and contexts.


.. code-block:: python

   from httpx import AsyncClient, HTTPError
   from safir.sentry import SentryWebException


   class FooServiceError(SentryWebException):
       """An error occurred sending a request to the foo service."""


   async def do_something(client: AsyncClient) -> None:
       # ... set up some request to the foo service ...
       try:
           r = await client.get(url)
           r.raise_for_status()
       except HTTPError as e:
           raise FooServiceError.from_exception(e) from e

This will set an ``httpx_request_info`` context with the body, and these tags if the info is available:

* ``httpx_request_method``
* ``gafaelfaw_user``
* ``httpx_request_url``
* ``httpx_request_status``

Testing
=======

Safir includes some functions to build `pytest`_ fixtures to assert you're sending accurate info with your Sentry events.

* `~safir.testing.sentry.sentry_init_fixture` will yield a function that can be used to initialize Sentry such that it won't actually try to send any events.
  It takes the same arguments as the `normal sentry init function <https://docs.sentry.io/platforms/python/configuration/options/>`_.
* `~safir.testing.sentry.capture_events_fixture` will return a function that will patch the sentry client to collect events into a container instead of sending them over the wire, and return the container.

These can be combined to create a pytest fixture that initializes Sentry in a way specific to your app, and passes the event container to your test function, where you can make assertions against the captured events.

.. code-block:: python
   :caption: conftest.py

   @pytest.fixture
   def sentry_items(
       monkeypatch: pytest.MonkeyPatch,
   ) -> Generator[Captured]:
       """Mock Sentry transport and yield a list that will contain all events."""
       with sentry_init_fixture() as init:
           init(
               traces_sample_rate=1.0,
               before_send=before_send,
           )
           events = capture_events_fixture(monkeypatch)
           yield events()

.. code-block:: python
   :caption: my_test.py

   def test_spawn_timeout(
       sentry_items: Captured,
   ) -> None:
       do_something_that_generates_an_error()

       # Check that an appropriate error was posted.
       (error,) = sentry_items.errors
       assert error["contexts"]["some_context"] == {
           "foo": "bar",
           "woo": "hoo",
       }
       assert error["exception"]["values"][0]["type"] == "SomeError"
       assert error["exception"]["values"][0]["value"] == (
           "Something bad has happened, do something!!!!!"
       )
       assert error["tags"] == {
           "some_tag": "some_value",
           "another_tag": "another_value",
       }
       assert error["user"] == {"username": "some_user"}

       # Check that an appropriate attachment was posted with the error.
       (attachment,) = sentry_items.attachments
       assert attachment.filename == "some_attachment.txt"
       assert "blah" in attachment.bytes.decode()

       transaction = sentry_items.transactions[0]
       assert transaction["spans"][0]["op"] == "some.operation"

On a `~safir.testing.sentry.Captured` container, ``errors`` and ``transactions`` are dictionaries.
Their contents are described in the `Sentry docs <https://develop.sentry.dev/sdk/data-model/event-payloads/>`_.
You'll probably make most of your assertions against the keys:
* ``tags``
* ``user``
* ``contexts``
* ``exception``

``attachments`` is a list of `~safir.testing.sentry.Attachment`.
