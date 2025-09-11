===================
Application metrics
===================

Safir provides helpers for publishing application metrics to Sasquatch_.
Using these helpers, your can instrument your app to push custom events to a Sasquatch-managed InfluxDB_ instance, and then use the Sasquatch-managed `Chronograf`_ to query and `graph them`_.

Support for application metrics publication via Kafka in Safir is optional.
To use it, depend on ``safir[kafka]``.

.. _InfluxDB: https://www.influxdata.com
.. _Chronograf: https://www.influxdata.com/time-series-platform/chronograf
.. _graph them: https://sasquatch.lsst.io/user-guide/dashboards.html

Application Resiliency
======================

.. warning::

   The app metrics functionality prioritizes the resiliency of your instrumented app over the reliability of sending app metrics.
   If your app metrics instrumentation gets into an error state during initialization, you will have to restart your app to start sending metrics again, even if the underlying infrastructure comes back up.

If the underlying app metrics infrastructure is degraded, like if Kafka or the Schema Registry are not available, the Safir app metrics code tries very hard to not crash or your instrumented application.

Instead of of raising exceptions, it will log error-level messages and put itself into an error state.
Once in this error state, it will not even try to interact with any underlying infrastructure, which means it will not even try to send metrics for a configurable amount of time.
It will instead only log error messages.

If this happens during initialization, you will have to restart your app after the underlying infrastructure is fixed to start sending metrics again.
If this happens after successful initialization, the app may start sending metrics again by itself after the underlying infrastructure is fixed.

The ``raise_on_error`` config option to ``KafkaMetricsConfiguration`` can be set to ``False`` to raise all exceptions to the instrumented app instead of swallowing them and logging errors.

The ``backoff_interval`` config option to ``KafkaMetricsConfiguration`` sets the amount of time to wait before trying to send metrics again if an error state is entered after initialization.

While in an error state, only one error message per attempted operation will be logged during a ``backoff_interval``, even if it is attempted multiple times.
For example, if an event manager gets into an error state, ``backoff_interval`` is set to 5 minutes, and 50 events are published in 1 minute, there will only be one error message logged.

Metrics vs. telemetry
=====================

Note that this system is not meant to handle *telemetry*.
Telemetry includes things like:

* The amount of CPU and Memory an app is using
* Kubernetes events and usage

Metrics, which this system deals with, are things like:

* A user generated a token.
  This event might include the username and token details.
* A user made a database query.
  This event might include the username, and type of query (sync vs async).
* A user starts a Nublado_ lab.
  This event might include the username, the size of the pod, and the image used.

For more details and examples of the difference between metrics and telemetery, see https://sqr-089.lsst.io/ (still in progress).

.. _Nublado: https://nublado.lsst.io

.. _metrics-example:

Full example
============

Here's an example of how you might use these tools in `typical FastAPI app`_. Individual components in this example are detailed in subsequent sections.

To publish events, you'll instantiate one of the subclasses of `~safir.metrics.EventManager`, generally `~safir.metrics.KafkaEventManager`.
When your app starts up, you'll use it to create an event publisher for every type of event that your app will publish.
Then, throughout your app, you'll call the `~safir.metrics.EventPublisher.publish` method on these publishers to publish individual events.

.. _typical FastAPI app: https://sqr-072.lsst.io/#one-design-pattern-for-fastapi-web-applications

Sasquatch config
----------------

Add your app to the `Sasquatch app metrics configuration`_!

Config
------

We need to put some config in our environment for the metrics functionality, a Kafka connection, and a schema registry connection.
The Kafka and schema manager values come from the Sasquatch configuration that you did and they usually are set in a Kubernetes ``Deployment`` template in your app's Phalanx_ config.

.. code-block:: shell

   METRICS_APPLICATION=myapp
   METRICS_EVENTS_TOPIC_PREFIX=what.ever
   KAFKA_SECURITY_PROTOCOL=SSL
   KAFKA_BOOSTRAP_SERVERS=sasquatch.kafka-1:9092,sasquatcy.kafka2-9092
   KAFKA_CLUSTER_CA_PATH=/some/path/ca.crt
   KAFKA_CLIENT_CERT_PATH=/some/path/user.crt
   KAFKA_CLIENT_KEY_PATH=/some/path/user.key
   SCHEMA_MANAGER_REGISTRY_URL=https://sasquatch-schema-registry.sasquatch:8081

Then we can use the metrics config helpers and the :ref:`Safir Kafka connection helpers <kafka-integration>` to write a Pydantic ``BaseSettings`` config model and singleton for our app.
Instantiating the model will pull values from the above environment variables.
See :ref:`configuration-details` for more info.

.. code-block:: python
   :caption: config.py

   from pydantic import Field, HttpUrl
   from pydantic_settings import BaseSettings, SettingsConfigDict
   from safir.metrics import (
       MetricsConfiguration,
       metrics_configuration_factory,
   )


   class Config(BaseSettings):
       model_config = SettingsConfigDict(
           env_prefix="MYAPP_", case_sensitive=False
       )

       an_important_url: HttpUrl = Field(
           ...,
           title="URL to something important",
       )

       metrics: MetricsConfiguration = Field(
           default_factory=metrics_configuration_factory,
           title="Metrics configuration",
       )


   config = Config()

Define events
-------------

Next, we need to:

* Define our event payloads
* Define and an events container that takes an `~safir.metrics.EventManager` and creates a publisher for each event our app will ever publish
* Instantiate an `~safir.dependencies.metrics.EventDependency`, which we'll initialize in our app start up laster.

We can do this all in an :file:`events.py` file.

.. note::

   Fields in metrics events can't be other models or other nested types like dicts, because the current event datastore (InfluxDB) does not support this.
   Basing our event payloads on `safir.metrics.EventPayload` will enable the `~safir.metrics.EventManager` to ensure at runtime when our events are registered that they don't contain incompatible fields.

.. note::

   Any ``timedelta`` fields will be serialized as an Avro ``double`` number of seconds.


.. code-block:: python
   :caption: metrics.py

   from enum import Enum
   from datetime import timedelta

   from pydantic import Field
   from safir.metrics import (
       EventManager,
       EventPayload,
   )
   from safir.dependencies.metrics import EventDependency, EventMaker


   class QueryType(Enum):
       async_ = "async"
       sync = "sync"


   class QueryEvent(EventPayload):
       """Information about a user-submitted query."""

       type: QueryType = Field(
           title="Query type", description="The kind of query"
       )

       duration: timedelta = Field(
           title="Query duration", description="How long the query took to run"
       )


   class Events(EventMaker):
       async def initialize(self, manager: EventManager) -> None:
           self.query = await manager.create_publisher("query", QueryEvent)


   # We'll call .initalize on this in our app start up
   events_dependency = EventDependency(Events())

.. _dataclasses-avroschema: https://marcosschroh.github.io/dataclasses-avroschema

Initialize
----------

Then, in a `FastAPI lifespan`_ function, we'll create an `safir.metrics.EventManager` and initialize our ``events_dependency`` with it.
We need to do this in a lifespan function, because we need to do it only once for our whole application, not once for each request.
In more complex apps, this would probably use the ProcessContext_ pattern.

.. code-block:: python
   :caption: main.py

   from contextlib import asynccontextmanager

   from fastapi import FastAPI
   from safir.metrics import EventManager

   from .config import config
   from .events import events_dependency


   @asynccontextmanager
   async def lifespan(app: FastAPI):
       event_manager = config.metrics.make_manager()
       await event_manager.initialize()
       await events_dependency.initialize(event_manager)

       yield

       await event_manager.aclose()


   app = FastAPI(lifespan=lifespan)

.. _FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/#lifespan
.. _ProcessContext: https://sqr-072.lsst.io/#process-context

Handlers
--------

In your handler functions, you can inject your events container as a `FastAPI dependency`_.
You can then publish events using the attributes on the dependency.
It is statically checked that calls to the publishers' `~safir.metrics.EventPublisher.publish` methods receive instances of the payload types that they were registered with.

In real apps:

* The injection would probably happen via a RequestContext_
* The request handling and event publishing would probably happen in a Service_

But the principle remains the same:

.. code-block:: python
   :caption: main.py (continued)

   from datetime import timedelta

   from fastapi import Depends
   from pydantic import BaseModel

   from .metrics import Events, events_dependency, QueryEvent
   from .models import QueryRequest  # Not shown


   @app.get("/query")
   async def query(
       query: QueryRequest,
       events: Annotated[Events, Depends(events_dependency)],
   ):
       duration: timedelta = do_the_query(query.type, query.query)
       await events.query.publish(
           QueryEvent(type=query.type, duration=duration)
       )

.. _FastAPI dependency: https://fastapi.tiangolo.com/tutorial/dependencies/
.. _RequestContext: https://sqr-072.lsst.io/#request-context
.. _Service: https://sqr-072.lsst.io/#services


Unit testing
============

Setting ``enabled`` to ``False`` and ``mock`` to ``True`` in your metrics configuration will give you a `safir.metrics.MockEventManager`.
This is a no-op event manager that produces publishers that record all of the events that they publish.
You can make assertions about these published events in your unit tests.

.. warning::

   Do not use the `safir.metrics.MockEventManager` in any deployed instance of your application.
   Recorded events are never cleaned up, and memory usage will grow unbounded.

.. code-block:: shell

   METRICS_APPLICATION=myapp
   METRICS_ENABLED=false
   METRICS_MOCK=true

.. code-block:: python

   from pydantic import ConfigDict

   from safir.metrics import (
       EventPayload,
       MockEventPublisher,
       metrics_configuration_factory,
   )


   config = metrics_configuration_factory()
   manager = config.make_manager()


   class SomeEvent(EventPayload):
       model_config = ConfigDict(ser_json_timedelta="float")

       foo: str
       count: int
       duration: float | None


   await manager.initialize()
   publisher = await manager.create_publisher("someevent", SomeEvent)

   await publisher.publish(SomeEvent(foo="foo1", count=1, duration=1.234))
   await publisher.publish(SomeEvent(foo="foo2", count=2, duration=2.345))
   await publisher.publish(SomeEvent(foo="foo3", count=3, duration=3.456))
   await publisher.publish(SomeEvent(foo="foo4", count=4, duration=None))
   await publisher.publish(SomeEvent(foo="foo5", count=5, duration=5.678))

   await manager.aclose()

   pub = cast(MockEventPublisher, pub).published

A mock publisher has an `safir.metrics.MockEventPublisher.published` attribute which is a `safir.metrics.PublishedList` containing of all of the `safir.metrics.EventPayload`'s published by that publisher.
A `safir.metrics.PublishedList` is a regular Python list with some mixed-in assertion methods.
All of these assertion methods take a list of dicts and compare them to the ``model_dump(mode="json")`` serialization of the published ``EventPayloads``.

``assert_published``
--------------------

Use `safir.metrics.PublishedList.assert_published` to assert that some set of payloads is an ordered subset of all of the payloads that were published, with no events in between.
If not, an exception (a subclass of `AssertionError`) will be raised.
Other events could have been published before or after the expected payloads.

.. code-block:: python

   pub.assert_published(
       [
           {"foo": "foo1", "count": 1, "duration": 1.234},
           {"foo": "foo2", "count": 2, "duration": 2.345},
           {"foo": "foo3", "count": 3, "duration": 3.456},
       ]
   )

You can also assert that the all of the expected payloads were published in any order, and possibly with events in between:

.. code-block:: python

   pub.assert_published(
       [
           {"foo": "foo1", "count": 1, "duration": 1.234},
           {"foo": "foo3", "count": 3, "duration": 3.456},
           {"foo": "foo2", "count": 2, "duration": 2.345},
       ],
       any_order=True,
   )

``assert_published_all``
------------------------

Use `safir.metrics.PublishedList.assert_published_all` to assert that the expected payloads, and only the expected payloads, were published:

.. code-block:: python

   pub.assert_published_all(
       [
           {"foo": "foo1", "count": 1, "duration": 1.234},
           {"foo": "foo2", "count": 2, "duration": 2.345},
           {"foo": "foo3", "count": 3, "duration": 3.456},
           {"foo": "foo4", "count": 4, "duration": None},
           {"foo": "foo5", "count": 5, "duration": 5.678},
       ],
   )

This would raise an exception because it is missing the ``foo5`` event:

.. code-block:: python

   pub.assert_published_all(
       [
           {"foo": "foo1", "count": 1, "duration": 1.234},
           {"foo": "foo2", "count": 2, "duration": 2.345},
           {"foo": "foo3", "count": 3, "duration": 3.456},
           {"foo": "foo4", "count": 4, "duration": None},
       ],
   )

You can use ``any_order`` here too:

.. code-block:: python

   pub.assert_published_all(
       [
           {"foo": "foo2", "count": 2, "duration": 2.345},
           {"foo": "foo5", "count": 5, "duration": 5.678},
           {"foo": "foo3", "count": 3, "duration": 3.456},
           {"foo": "foo1", "count": 1, "duration": 1.234},
           {"foo": "foo4", "count": 4, "duration": None},
       ],
       any_order=True,
   )

``ANY`` and ``NOT_NONE``
------------------------

You can use `safir.metrics.ANY` to indicate that any value, event `None` is OK.
This is just a re-export of `unittest.mock.ANY`.

.. code-block:: python

   from safir.metrics import ANY


   pub.assert_published_all(
       [
           {"foo": "foo3", "count": 3, "duration": ANY},
           {"foo": "foo4", "count": 4, "duration": ANY},
       ],
   )

You can use `safir.metrics.NOT_NONE` to indicate that any value except `None` is OK:

.. code-block:: python

   from safir.metrics import ANY


   pub.assert_published_all(
       [
           {"foo": "foo3", "count": 3, "duration": NOT_NONE},
           {"foo": "foo4", "count": 4, "duration": ANY},
       ],
   )

This would raise an exception, because ``duration`` for the ``foo4`` payload is `None`:

.. code-block:: python

   from safir.metrics import ANY


   pub.assert_published_all(
       [
           {"foo": "foo3", "count": 3, "duration": NOT_NONE},
           {"foo": "foo4", "count": 4, "duration": NOT_NONE},
       ],
   )

.. _configuration-details:

Configuration details
=====================

Initializing an ``EventManager`` requires some information about your app (currently just the name, and both Kafka_ and a `schema registry`_ clients.
Safir provides a configuration type and some `Pydantic BaseSettings`_ models to help get the necessary config for these things into your app via environment variables.

You'll need to provide some metrics-specific info, Kafka connection settings, and schema registry connection settings:

.. code-block:: shell

   export METRICS_APPLICATION=myapp
   export KAFKA_SECURITY_PROTOCOL=SSL
   export KAFKA_BOOSTRAP_SERVERS=sasquatch.kafka-1:9092,sasquatcy.kafka2-9092
   export KAFKA_CLUSTER_CA_PATH=/some/path/ca.crt
   export KAFKA_CLIENT_CERT_PATH=/some/path/user.crt
   export KAFKA_CLIENT_KEY_PATH=/some/path/user.key
   export SCHEMA_MANAGER_REGISTRY_URL=https://sasquatch-schema-registry.sasquatch:8081

To disable metrics at runtime, set ``METRICS_ENABLED`` to ``false``.
This will still verify that the event objects are valid, but will then discard them rather than trying to record them.

Your app doesn't use Kafka
--------------------------

If your app won't use Kafka for anything except publishing metrics, add a ``metrics`` member to your applications ``BaseSettings`` class with the type `~safir.metrics.MetricsConfiguration`.
This will become an appropriate instance of `~safir.metrics.BaseMetricsConfiguration` at runtime, based on the configuration from any of the normal sources that ``BaseSettings`` supports.

.. code-block:: python
   :caption: config.py

   from pydantic_settings import BaseSettings
   from safir.metrics import (
       MetricsConfiguration,
       metrics_configuration_factory,
   )


   class Config(BaseSettings):
       metrics: MetricsConfiguration = Field(
           default_factory=metrics_configuration_factory,
           title="Metrics configuration",
       )


   config = Config()
   manager = config.metrics.make_manager()

Unfortunately, due to limitations in Pydantic, you need to specify `~safir.metrics.metrics_configuration_factory` as a default factory.
This will choose an appropriate metrics configuration based on which environment variables are set.
This ``default_factory`` setting is not required if the configuration is provided via a YAML file or similar input with a ``metrics`` key, rather than purely via the environment.

Your app uses Kafka
-------------------

If your app uses Kafka for things other than metrics publishing (maybe it's a FastStream_ app), you can pass an existing FastStream Kafka broker to `~safir.metrics.BaseMetricsConfiguration.make_manager`.
This broker will be used rather than creating a new one, and it will not be started or stopped by the `~safir.metrics.EventManager`.

.. code-block:: python
   :caption: config.py

   from aiokafka.admin.client import AIOKafkaAdminClient
   from faststream.kafka import KafkaBroker
   from pydantic_settings import BaseSettings
   from safir.metrics import (
       KafkaClients,
       MetricsConfiguration,
       metrics_configuration_factory,
   )


   class Config(BaseSettings):
       metrics: MetricsConfiguration = Field(
           default_factory=metrics_configuration_factory,
           title="Metrics configuration",
       )


   config = Config()
   kafka_broker = KafkaBroker(...)  # created elsewhere by your application
   manager = config.metrics.make_manager(kafka_broker=kafka_broker)

This is the recommended approach when reusing a Kafka broker since `~safir.metrics.BaseMetricsConfiguration.make_manager` will still honor the metrics configuration and create no-op or mock event managers if requested, in which case the provided Kafka broker will be ignored.
An internal Kafka admin client and schema manager client will still be created and managed by the event manager in this case.

If you want full manual control, you can create the event manager directly and provide a Kafka broker, admin client, and schema manager.

.. code-block:: python

   from aiokafka.admin.client import AIOKafkaAdminClient
   from faststream.kafka import kafkaBroker
   from safir.kafka import KafkaConnectionSettings, SchemaManagerSettings
   from safir.metrics import EventsConfiguration, KafkaEventManager

   kafka_config = KafkaConnectionSettings()
   schema_manager_config = SchemaManagerSettings()
   events_config = EventsConfiguration()

   # You can use this in all parts of your app
   broker = KafkaBroker(**kafka_config.to_faststream_params())

   admin_client = AIOKafkaAdminClient(**kafka_config.to_aiokafka_params())
   schema_manager = schema_manager_config.make_manager()

   event_manager = KafkaEventManager(
       application="myapp",
       topic_prefix=events_config.topic_prefix,
       kafka_broker=broker,
       kafka_admin_client=admin_client,
       schema_manager=schema_manager,
       manage_kafka_broker=False,
   )

Setting ``manage_kafaka`` to `False` here means that calling `~safir.metrics.EventManager.aclose` on your `~safir.metrics.EventManager` will not start or stop the Kafka broker.
You are expected to do this yourself somewhere else in your app.
However, the `~safir.metrics.KafkaEventManager` will start and stop the Kafka admin client.
