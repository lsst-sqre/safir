############################################################
Managing remote schema registry schemas with Pydantic Models
############################################################

Safir provides a ``PydanticSchemaManager`` to register and evolve Avro schemas in a Confluent-compatible `schema registry`_ via `Pydantic`_ models.
Specifically, it can:

* Create schemas in the registry
* Create new versions of schemas in the registry from changes in the Pydantic models, while validating that those changes are compatible with the compatibility strategies specified in the registry
* Serialize Pydantic model instances to `Avro`_ schemas with the registry's schema ID

Interactions with the remote registry are cached, so your app will rarely have to make calls to it after initialization.

.. _Avro: https://avro.apache.org/
.. _schema registry: https://docs.confluent.io/platform/current/schema-registry/index.html

Configuring a schema registry client
====================================

The ``PydanticSchemaManager`` interacts with the schema registry through a `python-schema-registry-client`_ `AsyncSchemaRegistryClient`_.
You can use the ``SchemaRegistryConnectionSettings`` `Pydantic settings`_ model to take settings from environment variables and construct this client.
The ``SchemaRegistryConnectionSettings`` model will try to find its attributes from ``SCHEMA_REGISTRY_``-prefixed environment variables:

.. code-block:: shell-session

   $ export SCHEMA_REGISTRY_URL=https://sasquatch-schema-registry.sasquatch:8081
.. code-block:: python

   from safir.kafka import SchemaRegistryConnectionSettings
   from schema_registry.client import AsyncSchemaRegistryClient

   config = SchemaRegistryConnectionSettings()
   registry = AsyncSchemaRegistryClient(**config.schema_registry_client_params)

.. _Pydantic settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
.. _python-schema-registry-client: https://github.com/marcosschroh/python-schema-registry-client
.. _AsyncSchemaRegistryClient: https://marcosschroh.github.io/python-schema-registry-client/client/#schema_registry.client.AsyncSchemaRegistryClient

Using the manager
=================

Before you can serialize model instances, you need to register the model class with the manager.
Models must be subclasses of `AvroBaseModel`_ from `dataclasses-avroschema`_. Then, you can serialize instances of the model into Avro messages with the registry schema ID embeded in them.

.. code-block:: python

   import asyncio

   from dataclasses_avroschema.pydantic import AvroBaseModel
   from safir.kafka import (
       SchemaRegistryConnectionSettings,
       PydanticSchemaManager,
   )
   from schema_registry.client import AsyncSchemaRegistryClient


   async def main() -> None:
       # Construct a manager
       config = SchemaRegistryConnectionSettings()
       registry = AsyncSchemaRegistryClient(
           **config.schema_registry_client_params
       )
       manager = PydanticSchemaManager(registry=registry)

       # Define a model
       class MyModel(AvroBaseModel):
           field1: int = Field(default=0)
           field2: str

       # Register your model, which will:
       #
       # * Create the schema in the registry if it doesn't exist
       # * Create a new version of the schema in the registry if this model has
       #   changed since #   the last time it was registered
       # * Do nothing if the schema already exists in the registry and the
       #   model hasn't changed.
       await manager.register(MyModel)

       # Serialize an instance
       instance = MyModel(field1=1, field2="woohoo!")
       avro: bytes = manager.serialize(instance)


   asyncio.run(main())

You probably want to register all of your models at the start of your application so that:

* Any schema registry lookups are cached before your app starts doing stuff
* Any incompatible changes you have made to the models will prevent the app from starting

.. _AvroBasemodel: https://marcosschroh.github.io/dataclasses-avroschema/pydantic/
.. _dataclasses-avroschema: https://github.com/marcosschroh/dataclasses-avroschema

Compatibility
-------------

One of the main benefits of using the schema registry is that it can tell you if you try to update a schema in a way that is incompatible with how other users of the schema are expecting it to be updated.
The specific changes that are incompatible could vary from subject to subject, and depend on that subject's `compatibility type`_.

You can specify the compatibility type when registering a model.
If you don't specify a compatibility type, the subject will have the default compatibility type set on the schema registry server.

Once the initial version of the schema is created, if you change the model in your app in an incompatible way and try to register it again, the manager will throw an ``IncompatibleSchemaError``.

.. code-block:: python

   from safir.kafka import (
       IncompatibleSchemaError,
       SchemaRegistryCompatibility,
       PydanticSchemaManager,
   )

   manager: PydanticSchemaManager


   class MyModel(AvroBaseModel):
       field1: int
       field2: str


   await manager.register(
       MyModel, compatibility=SchemaManagerCompatibility.FORWARD
   )

.. code-block:: python

   manager: PydanticSchemaManager


   # sometime in the future, this model changes like this
   class MyModel(AvroBaseModel):
       field1: int


   # This will throw an exception!
   await manager.register(MyModel)

.. _compatibility type: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html#compatibility-types

Subject names
-------------

The `subject`_ that a schema is registered under is completely independent of any Kafka topics that serialized messages may or may not be published to.
In other words, it uses the `RecordNameStrategy`_.
The manager uses the combined Avro namespace and record name as the subject name.
The record name and namespace come from the name of the model class, and/or certain fields on an inner class named ``Meta``:

* ``schema_name``
* ``namespace``

.. code-block:: python

   # subject: "MyModel"
   class MyModel(AvroBaseModel):
       str_field: str
       int_field: int


.. code-block:: python

   # subject: "mymodelcustom"
   class MyModel(AvroBaseModel):
       str_field: str
       int_field: int

       class Meta:
           schema_name = "mymodelcustom"

.. code-block:: python

   # subject: my.namespace.mymodelcustom
   class MyModel(AvroBaseModel):
       str_field: str
       int_field: int

       class Meta:
           schema_name = "mymodelcustom"
           namespace = "my.namespace"

.. code-block:: python

   # subject: my.namespace.MyModel
   class MyModel(AvroBaseModel):
       str_field: str
       int_field: int

       class Meta:
           namespace = "my.namespace"

.. _subject: https://docs.confluent.io/platform/current/schema-registry/fundamentals/index.html#schemas-subjects-and-topics
.. _RecordNameStrategy: https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html#sr-schemas-subject-name-strategy

Subject suffixes for development
================================

When you're developing and testing your app, you probably don't want to register new versions of its schemas in the subjects that actual deployed versions of the app are using.
You can instantiate the ``PydanticSchemaManager`` with a ``suffix`` argument to add that suffix onto all subjects used by the manager:

.. code-block:: python

   registry: AsyncSchemaRegistryClient
   manager = PydanticSchemaManager(registry=registry, suffix="_testing")


   # subject: my.namespace.mymodelcustom_testing
   class MyModel(AvroBaseModel):
       str_field: str
       int_field: int

       class Meta:
           schema_name = "mymodelcustom"
           namespace = "my.namespace"


   # subject: my.namespace.MyModel_testing
   class MyModel(AvroBaseModel):
       str_field: str
       int_field: int

       class Meta:
           namespace = "my.namespace"


   # ...etc.

You shouldn't use suffixes in production environments.
