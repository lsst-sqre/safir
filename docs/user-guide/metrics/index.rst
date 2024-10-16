===================
Application metrics
===================

Safir provides helpers for publishing application metrics to Sasquatch_.
Using these helpers, your can instrument your app to push custom events to a Sasquatch-managed InfluxDB_ instance, and then use the Sasquatch-managed `Chronograf`_ to query and `graph them`_.

.. _InfluxDB: https://www.influxdata.com
.. _Chronograf: https://www.influxdata.com/time-series-platform/chronograf
.. _graph them: https://sasquatch.lsst.io/user-guide/dashboards.html

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

Full example
============

Here's an example of how you might use these tools in `typical FastAPI app`_. Individual components in this example are detailed in subsequent sections.

To publish events, you'll instantiate an `~safir.metrics.EventManager`.
When your app starts up, you'll use it to create an event publisher for every kind of event that your app will publish.
Then, throughout your app, you'll call the `~safir.metrics.EventPublisher.publish` method on these publishers to publish individual events.

.. _typical FastAPI app: https://sqr-072.lsst.io/#one-design-pattern-for-fastapi-web-applications

Sasquatch config
----------------

Add your app to the `Sasquatch app metrics configuration`_!

.. _Sasquatch app metrics configuration: https://sasquatch.lsst.io/user-guide/app-metrics.html

Config
------

We need to put some config in our environment for the metrics functionality, a Kafka connection, and a schema registry connection.
The Kafka and schema manager values come from the Sasquatch configuration that you did and they usually are set in a Kubernetes ``Deployment`` template in your app's Phalanx_ config.

.. code-block:: shell

   METRICS_APP_NAME=myapp
   KAFKA_SECURITY_PROTOCOL=SSL
   KAFKA_BOOSTRAP_SERVERS=sasquatch.kafka-1:9092,sasquatcy.kafka2-9092
   KAFKA_CLUSTER_CA_PATH=/some/path/ca.crt
   KAFKA_CLIENT_CERT_PATH=/some/path/user.crt
   KAFKA_CLIENT_KEY_PATH=/some/path/user.key
   SCHEMA_MANAGER_REGISTRY_URL=https://sasquatch-schema-registry.sasquatch:8081

Then we can use the metrics config helpers and the :ref:`Safir Kafka connection helpers <kafka-integration>` to write a Pydantic BaseSettings config model and singleton for our app.
Instantiating the model will pull values from the above environment variables.
See :ref:`configuration-details` for more info.

.. code-block:: python
   :caption: config.py

   from pydantic import Field, HttpUrl
   from pydantic_settings import BaseSettings, SettingsConfigDict
   from safir.metrics import KafkaMetricsConfiguration


   class Configuration(BaseSettings):
       an_important_url: HttpUrl = Field(
           ...,
           title="URL to something important",
       )

       metrics: KafkaMetricsConfiguration(
           default_factory=KafkaMetricsConfiguration
       )

       model_config = SettingsConfigDict(
           env_prefix="MYAPP_", case_sensitive=False
       )


   config = Configuration()

Define events
-------------

Next, we need to:

* Define our event payloads
* Define and an events container that takes an `~safir.metrics.EventManager` and creates a publisher for each event our app will ever publish
* Instantiate an `~safir.dependencies.metrics.EventDependency`, which we'll initialize in our app start up laster.

We can do this all in an ``events.py`` file.

.. note::

   Fields in metrics events can't be other models or other nested types like dicts, because the current event datastore (InfluxDB) does not support this.
   Basing our event payloads on `safir.metrics.EventPayload` will enable the `~safir.metrics.EventManager` to ensure at runtime when our events are registered that they don't contain incompatible fields.

.. warning::

   `dataclasses-avroschema`_ does not currently support timedelta fields, and will throw an exception if you define a field of type ``timedelta`` in your event payload model.
   To work around this, you can declare any ``timedelta`` fields as type `~safir.metrics.EventDuration`.
   You can pass a ``timedelta`` object as a value, and the field will serialize to the float number of seconds represented by the duration.
   You can only use this type in models that are subclasses of `~safir.metrics.EventPayload`.

.. code-block:: python
   :caption: metrics.py

   from enum import Enum
   from datetime import timedelta

   from pydantic import Field
   from safir.metrics import (
       EventDuration,
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

       duration: EventDuration = Field(
           title="Query duration", description="How long the query took to run"
       )


   class Events(EventMaker):
       def initialize(manager: EventManager) -> None:
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

.. _configuration-details:

Configuration details
=====================

Initializing an ``EventManager`` requires some information about your app (currently just the name, and both Kafka_ and a `schema registry`_ clients.
Safir provides some `Pydantic BaseSettings`_ models to help get the necessary config for these things into your app via environment variables.

You'll need to provide some metrics-specific info, Kafka connection settings, and schema registry connection settings:

.. code-block:: shell

   export METRICS_APP_NAME=myapp
   export METRICS_DISABLE=false
   export KAFKA_SECURITY_PROTOCOL=SSL
   export KAFKA_BOOSTRAP_SERVERS=sasquatch.kafka-1:9092,sasquatcy.kafka2-9092
   export KAFKA_CLUSTER_CA_PATH=/some/path/ca.crt
   export KAFKA_CLIENT_CERT_PATH=/some/path/user.crt
   export KAFKA_CLIENT_KEY_PATH=/some/path/user.key
   export SCHEMA_MANAGER_REGISTRY_URL=https://sasquatch-schema-registry.sasquatch:8081


Your app doesn't use Kafka
--------------------------

If your app won't use Kafka for anything except publishing metrics, there is another config helper, `~safir.metrics.KafkaMetricsConfiguration` that will construct an ``EventManager`` and all of its Kafka dependencies:


.. code-block:: python

   from safir.metrics import EventManager, MetricsConfiguration

   config = KafkaMetricsConfiguration()
   manager = config.make_manager()

Your app uses Kafka
-------------------

If your app uses Kafka for things other than metrics publishing (maybe it's a FastStream_ app), you can use the :ref:`Safir Kafka connection helpers <kafka-integration>` to create clients and pass them to the `~safir.metrics.EventManager` constructor.

.. note::

   The ``manage_kafaka`` parameter is ``False`` here.  This means that calling `~safir.metrics.EventManager.aclose` on your `~safir.metrics.EventManager` will NOT stop the Kafka clients.
   You are expected to do this yourself somewhere else in your app.

.. code-block:: python

   from safir.kafka import KafkaConnectionSettings, SchemaManagerSettings
   from safir.metrics import EventManager, MetricsConfiguration

   kafka_config = KafkaConnectionSettings()
   schema_manager_config = SchemaManagerSettings()
   metrics_config = MetricsConfiguration()

   # You can use this in all parts of your app
   broker = KafkaBroker(**kafka_config.to_faststream_params())

   admin_client = AIOKafkaAdminClient(
       **kafka_config.to_aiokafka_params(),
   )
   schema_manager = schema_manager_config.make_manager()

   return EventManager(
       app_name=metrics_config.app_name,
       base_topic_prefix=metrics_config.topic_prefix,
       kafka_broker=broker,
       kafka_admin_client=admin_client,
       schema_manager=schema_manager,
       manage_kafka=False,
       disable=self.metrics_events.disable,
   )

.. _FastStream: https://faststream.airt.ai
