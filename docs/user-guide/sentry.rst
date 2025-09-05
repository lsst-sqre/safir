##################
Integrating Sentry
##################

Sentry_ is an exception reporting and tracing observability service.
It has great out-of-the-box integrations with many of the Python libaries that we use, including FastAPI_, SQLAlchemy_, and arq_.
Most apps can get a lot of value out of Sentry by doing nothing other than calling the `init function <https://docs.sentry.io/platforms/python/#configure>`_ early in their app and using some of the helpers described here.

Instrumenting your application
==============================

The simplest instrumentation involves calling ``sentry_sdk.init`` as early as possible in your app's :file:`main.py` file.
You will need to provide at least:

* A Sentry DSN associated with your app's Sentry project
* An environment name with which to tag Sentry events

You can optionally provide:

* The `~safir.sentry.before_send_handler` before_send_ handler, which adds the environment to the Sentry fingerprint, and handles :ref:`sentry-exception-types` appropriately.
* A value to configure the traces_sample_rate_ so you can easily enable or disable tracing from Phalanx without changing your app's code
* A `release`_ that will be added to all events to identify which version of the application generated the event.
* Other `configuration options`_.

The `~safir.sentry.initialize_sentry` function will parse the DSN, environment, and optionally the traces sample rate from environment variables.
It takes a ``release`` parameter.
For most Safir applications, you should pass the value in ``<your application>.__version__``, which is the version discovered by `setuptools-scm`_.
It will then call ``sentry_sdk.init`` with those values and the `~safir.sentry.before_send_handler` `before_send`_ handler.
The config values are taken from enviroment variables and not the main app config class because we want to initialize Sentry before the app configuration is initialized, especially in apps that load their config from YAML files.

Your app's `Kubernetes workload`_ template needs to specify these environment variables and their values, which might look like this:

.. code-block:: yaml
   :caption: deployment.yaml

   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: "myapp"
   spec:
     template:
       spec:
         containers:
           - name: "app"
             env:
               {{- if .Values.sentry.enabled }}
               - name: "SENTRY_DSN"
                 valueFrom:
                   secretKeyRef:
                     name: "myapp"
                     key: "sentry-dsn"
               - name: "SENTRY_ENVIRONMENT"
                 value: {{ .Values.global.environmentName }}
               {{- end }}

And your :file:`main.py` might look like this:

.. code-block:: python
   :caption: src/myapp/main.py

   import sentry_sdk

   from safir.sentry import initialize_sentry

   import myapp
   from .config import config

   initialize_sentry(release=myapp.__version__)


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncGenerator: ...


   app = FastAPI(title="My App", lifespan=lifespan, ...)

.. _before_send: https://docs.sentry.io/platforms/python/configuration/options/#before_send
.. _traces_sample_rate: https://docs.sentry.io/platforms/python/configuration/options/#traces_sample_rate
.. _setuptools-scm: https://github.com/pypa/setuptools-scm
.. _configuration options: https://docs.sentry.io/platforms/python/configuration/options/
.. _release: https://docs.sentry.io/product/releases/
.. _Kubernetes workload: https://kubernetes.io/docs/concepts/workloads/

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

   `Tags <https://docs.sentry.io/platforms/python/enriching-events/tags/>`_ are short key-value pairs that are indexed by Sentry.
   Use tags for small values that you would like to search by and aggregate over when analyzing multiple Sentry events in the Sentry UI.
   `Contexts <https://docs.sentry.io/platforms/python/enriching-events/context/>`_ are for more detailed information related to single events.
   You can not search by context values, but you can store more data in them.
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

Similar to :ref:`slack-web-exceptions`, you can use `~safir.sentry.SentryWebException` to report an httpx_ exception with helpful info in tags and contexts.

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

* ``gafaelfawr_user``
* ``httpx_request_method``
* ``httpx_request_url``
* ``httpx_request_status``

Testing
=======

Safir includes some functions to build pytest_ fixtures to assert you're sending accurate info with your Sentry events.

* `~safir.testing.sentry.sentry_init_fixture` will yield a function that can be used to initialize Sentry such that it won't actually try to send any events.
  It takes the same arguments as the `normal sentry init function <https://docs.sentry.io/platforms/python/configuration/options/>`_.
* `~safir.testing.sentry.capture_events_fixture` will return a function that will patch the sentry client to collect events into a container instead of sending them over the wire, and return the container.

These can be combined to create a pytest fixture that initializes Sentry in a way specific to your app, and passes the event container to your test function, where you can make assertions against the captured events.

.. code-block:: python
   :caption: conftest.py

   @pytest.fixture
   def sentry_items(monkeypatch: pytest.MonkeyPatch) -> Generator[Captured]:
       """Mock Sentry transport and yield a list of all published events."""
       with sentry_init_fixture() as init:
           init(traces_sample_rate=1.0, before_send=before_send)
           events = capture_events_fixture(monkeypatch)
           yield events()

.. code-block:: python
   :caption: my_test.py

   def test_spawn_timeout(sentry_items: Captured) -> None:
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
