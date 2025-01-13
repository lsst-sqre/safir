##################
Helpers for Sentry
##################

`Sentry`_ is an exception reporting and tracing observability service.
It has great out-of-the-box integrations with many of the Python libaries that we use, including `FastAPI`_, `SqlAlchemy`_, and `arq`_.
Most apps can get a lot of value out of Sentry by doing nothing other than calling the `init function <https://docs.sentry.io/platforms/python/#configure>`_ early in their app and using some of the helpers described here.

``before_send`` handlers
========================

In the init function, you can specify a function to run before an event is sent to Sentry.
Safir has some useful functions you can use as ``before_send`` handlers.

before_send_handler
-------------------

.. note::

   You should probably use this handler in all of your safir apps.

This adds the environment to the Sentry fingerprint, and handles :ref:`sentry-exception-types` appropriately.
It is a combination of the :ref:`fingerprint-env-handler` and :ref:`sentry-exception-handler` functionality.

.. code-block:: python

   from safir.sentry import before_send_handler, SentryException


   sentry_sdk.init(before_send=before_send_handler)


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

This will send an event to sentry that will properly trigger an event for every environment, and will have ``some_tag`` and ``some_context`` attached.

.. _fingerprint-env-handler:

fingerprint_env_handler
-----------------------

Alerts that are set to fire when an issue is first created, or regressed, will do so once an event that matches that issue occurs in `ANY environment <https://github.com/getsentry/sentry/issues/21612>`_, not every environment.
This means that if an the first event from an issue comes from a development environment, the alert will be triggered, and will not trigger again when the first event comes from a production environment.
To have such an alert trigger per-environment, we need to `change the fingerprint of the event <https://github.com/getsentry/sentry/issues/64354#issuecomment-1927839632>`_ to include the environment, which is what the `~safir.sentry.fingerprint_env_handler` does.

.. _sentry-exception-handler:

sentry_exception_handler
------------------------

In order to get the tags and contexts from the :ref:`sentry-exception-types` on events, you have to use this handler.


.. code-block:: python

   from safir.sentry import sentry_exception_handler, SentryException
   import sentry_sdk


   sentry_sdk.init(before_send=sentry_exception_handler)


   class SomeError(SentryException): ...


   exc = SomeError("Some error!")
   exc.tags["some tag"] = "some value"
   exc.contexts["some context"] = {"foo": "bar"}

   raise exc

Without the `~safir.sentry.sentry_exception_handler` passed to ``before_send``, ``some tag`` and ``some context`` would not show up the error event sent to sentry from ``raise exc``.

.. _sentry-exception-types:

Special Sentry exception types
==============================

Similar to :ref:`slack-exceptions`, you can use `~safir.sentry.SentryException` to create custom exceptions that will send specific Sentry tags and contexts with any events that arise from them.
You need to use the :ref:`sentry-exception-handler` ``before_send`` hook for this to work.

SentryException
---------------

You can define custom exceptions that inherit from `~safir.sentry.SentryException`.
These exceptions will have ``tags`` and ``contexts`` attributes.
If Sentry sends an event that arises from reporting one of these exceptions, the event will have those tags and contexts attached to it.

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

* `~safir.sentry.sentry_init_fixture` will yield a function that can be used to initialize Sentry such that it won't actually try to send any events.
  It takes the same arguments as the `normal sentry init function <https://docs.sentry.io/platforms/python/configuration/options/>`_.
* `~safir.sentry.capture_events_fixture` will return a function that will patch the sentry client to collect events into a container instead of sending them over the wire, and return the container.

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
       (attacument,) = sentry_items.attachments
       assert attachment.filename == "some_attachment.txt"
       assert "blah" in attachment.bytes.decode()

       transaction = sentry_items.transactions[0]
       assert transaction["spans"][0]["op"] == "some.operation"

On a `~safir.sentry.Captured` container, ``errors`` and ``transactions`` are dictionaries.
Their contents are described in the `Sentry docs <https://develop.sentry.dev/sdk/data-model/event-payloads/>`_.
You'll probably make most of your assertions against the keys:
* ``tags``
* ``user``
* ``contexts``
* ``exception``

``attachments`` is a list of `~safir.sentry.Attachment`.
