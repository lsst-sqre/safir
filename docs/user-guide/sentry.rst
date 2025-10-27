##################
Integrating Sentry
##################

Sentry_ is an exception reporting and tracing observability service.
It has great out-of-the-box integrations with many of the Python libaries that we use, including FastAPI_, SQLAlchemy_, and arq_.
Most apps can get a lot of value out of Sentry by doing nothing other than calling the `init function <https://docs.sentry.io/platforms/python/#configure>`_ early in their app and using some of the helpers described here.

.. _sentry-instrumentation:

Instrumenting your application
==============================

The simplest instrumentation involves calling ``sentry_sdk.init`` as early as possible in your app's :file:`main.py` file.
You will need to provide at least:

* A Sentry DSN associated with your app's Sentry project
* An environment name with which to tag Sentry events

You can optionally provide:

* The `~safir.sentry.before_send_handler` before_send_ handler, which adds the environment to the Sentry fingerprint, and handles :ref:`sentry-exceptions` appropriately.
* A value to configure the traces_sample_rate_ so you can easily enable or disable tracing from `Phalanx`_ without changing your app's code
* A `release`_ that will be added to all events to identify which version of the application generated the event.
* Other `configuration options`_.

The `~safir.sentry.initialize_sentry` function will parse the DSN, environment, and optionally the traces sample rate from environment variables.
It takes a ``release`` parameter.
For most Safir applications, you should pass the value in ``<your application>.__version__``, which is the version discovered by `setuptools-scm`_.
It will then call ``sentry_sdk.init`` with those values and the `~safir.sentry.before_send_handler` `before_send`_ handler.
The config values are taken from enviroment variables and not the main app config class because we want to initialize Sentry before the app configuration is initialized, especially in apps that load their config from YAML files. These environment variables are described in the `~safir.sentry.SentryConfig` model.

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
               - name: "SENTRY_TRACES_SAMPLE_RATE"
                 value: {{ .Values.sentry.tracesSampleRate }}
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

.. _sentry-exceptions:

Adding Sentry metadata to SlackExceptions
=========================================

You can enrich :ref:`slack-exceptions` to send specific Sentry `tags`_, `contexts`_, and `attachments`_ with any events that arise from them.
You need to use the `~safir.sentry.before_send_handler` handler for this to work.

.. _tags: https://docs.sentry.io/platforms/python/enriching-events/tags/
.. _contexts: https://docs.sentry.io/platforms/python/enriching-events/context/
.. _attachments: https://docs.sentry.io/platforms/python/enriching-events/attachments/

To do this, define a ``to_sentry`` method on any custom exception that inherits from `~safir.slack.blockkit.SlackException`.
This method returns a `~safir.slack.sentry.SentryEventInfo` object with ``tags``, ``contexts``, ant ``attachments`` attributes.
These attributes can be set from attributes on the exception object, or any other way you want.
If Sentry sends an event that arises from reporting one of these exceptions, the event will have those tags, contexts, and attachments attached to it.

.. note::

   Tags are short key-value pairs that are indexed by Sentry.
   Use tags for small values that you would like to search by and aggregate over when analyzing multiple Sentry events in the Sentry UI.
   Contexts can hold more text, and are for more detailed information related to single events.
   Attachments can hold the most text, but are the hardest to view in the Sentry UI.
   You can not search by context or attachment values, but you can store more data in them.
   You should use a tag for something like ``"query_type": "sync"``, a context for something like ``"query_info": {"query_text": text}``, and an attachment for something like an HTTP response body.

.. code-block:: python

   from typing import override

   from safir.sentry import initialize_sentry
   from safir.slack.blockkit import SlackException


   initialize_sentry()


   class SomeError(SlackException):
       def __init__(
           self, message: str, short: str, medium: str, long: str
       ) -> None:
           super.__init__(message)
           self.short = short
           self.medium = medium
           self.long = long

       @override
       def to_slack(self):
           # Construct a SlackMessage
           pass

       @override
       def to_sentry(self):
           info = super().to_sentry()
           info.tags["some_tag"] = self.short
           info.contexts["some_context"] = {"some_item": self.medium}
           info.attachments["some_attachment"] = self.long


   raise SomeError(
       "Some error!",
       short="some_value",
       medium="some longer value...",
       long="A large bunch of text...............",
   )

.. _notification-helper:

Notification helper
-------------------

You should implement both `~safir.slack.blockkit.SlackException.to_slack` and `~safir.slack.blockkit.SlackException.to_sentry` on your exceptions, since many Phalanx installations will use either Sentry or Slack for error notifications, but not both.
The Sentry SDK and `~safir.slack.webhook.SlackRouteErrorHandler` will report uncaught exceptions to each service.
When you want to handle Exceptions but still send notifications for them, Safir provides the `~safir.sentry.report_exception` function. This will notify Slack, or Sentry, or both, depending on which services are configured and initialized.

.. code-block:: python

   from typing import override

   import structlog

   from safir.sentry import initialize_sentry, report_exception
   from safir.slack.blockkit import SlackException
   from safir.slack.webhook import SlackWebhookClient

   initialize_sentry()

   logger = structlog.get_logger(__file__)
   slack_client = SlackWebhookClient(mock_slack.url, "App", logger)


   class SomeError(SlackException):
       def __init__(
           self, message: str, short: str, medium: str, long: str
       ) -> None:
           super.__init__(message)
           self.short = short
           self.medium = medium
           self.long = long

       @override
       def to_slack(self):
           # Construct a SlackMessage
           pass

       @override
       def to_sentry(self):
           info = super().to_sentry()
           info.tags["some_tag"] = self.short
           info.contexts["some_context"] = {"some_item": self.medium}
           info.attachments["some_attachment"] = self.long


   try:
       raise SomeError(
           "Some error!",
           short="some_value",
           medium="some longer value...",
           long="A large bunch of text...............",
       )
   except SomeError as exc:
       await report_exception(exc, slack_client=slack_client)

   print("SomeError happened, but we're continuing.")


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
       assert attachment.filename == "some_attachment"
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
