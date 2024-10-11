#####################################################
Managing schema registry schemas with Pydantic Models
#####################################################

Safir provides a `~safir.kafka.PydanticSchemaManager` to register and evolve Avro schemas in a Confluent-compatible `schema registry`_ via Pydantic_ models.
Specifically, it can:

* Create schemas in the registry
* Create new versions of schemas in the registry from changes in the Pydantic models, while validating that those changes are compatible with the compatibility strategies specified in the registry
* Serialize Pydantic model instances to Avro_ schemas with the registry's schema ID

Interactions with the remote registry are cached, so your app will rarely have to make calls to it after initialization.

.. _Avro: https://avro.apache.org/

Constructing the manager
========================

You can use the `~safir.kafka.SchemaManagerSettings` `Pydantic settings`_ model to take settings from environment variables and construct a .`~safir.kafka.PydanticSchemaManager` with the `~safir.kafka.SchemaManagerSettings.make_manager` method.
The `~safir.kafka.SchemaManagerSettings` model will try to find its attributes from ``SCHEMA_MANAGER``-prefixed environment variables:

.. code-block:: shell-session

   $ export SCHEMA_MANAGER_REGISTRY_URL=https://sasquatch-schema-registry.sasquatch:8081

.. code-block:: python

   from safir.kafka import SchemaManagerSettings

   config = SchemaManagerSettings()
   manager = config.make_manager()

You can also construct the manager manually by giving it an instance of `~schema_registry.client.AsyncSchemaRegistryClient`:

.. code-block:: python

   from safir.kafka import PydanticSchemaManager
   from schema_registry.client import AsyncSchemaRegistryClient

   registry = AsyncSchemaRegistryClient(url="https://some.url")
   manager = PydanticSchemaManager(registry=registry)

.. _Pydantic settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/

Using the manager
=================

Before you can serialize model instances, you need to register the model class with the manager.
Models must be subclasses of AvroBaseModel_ from dataclasses-avroschema_. Then, you can serialize instances of the model into Avro messages with the registry schema ID embeded in them.

.. code-block:: python

   from dataclasses_avroschema.pydantic import AvroBaseModel


   # Define a model
   class MyModel(AvroBaseModel):
       field1: int = Field(default=0)
       field2: str


   # Register your model, which will:
   #
   # * Create the schema in the registry if it doesn't exist
   # * Create a new version of the schema in the registry if this model has
   #   changed since the last time it was registered
   # * Do nothing if the schema already exists in the registry and the
   #   model hasn't changed.
   await manager.register(MyModel)

   # Serialize an instance
   instance = MyModel(field1=1, field2="woohoo!")
   avro: bytes = manager.serialize(instance)

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

Once the initial version of the schema is created, if you change the model in your app in an incompatible way and try to register it again, the manager will throw an `~safir.kafka.IncompatibleSchemaError`.

.. warning::

   Do not deploy your application to an ``int`` or ``dev`` environment until any changes to your schema are finalized!
   If an incorrect version of a schema gets registered in one of these environments, and the corrected schema is incompatible with the the incorrect one, you will have to manually delete the incorrect version from the registry.

.. code-block:: python

   from safir.kafka import (
       IncompatibleSchemaError,
       SchemaRegistryCompatibility,
       PydanticSchemaManager,
   )


   class MyModel(AvroBaseModel):
       field1: int
       field2: str


   await manager.register(
       MyModel, compatibility=SchemaManagerCompatibility.FORWARD
   )

Sometime in the future, if the model changes like this, an exception will be raised upon registration:

.. code-block:: python

   class MyModel(AvroBaseModel):
       field1: int


   # This will throw an exception!
   await manager.register(MyModel)

.. _compatibility type: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html#compatibility-types

Subject names
-------------

The subject_ that a schema is registered under is completely independent of any Kafka topics that serialized messages may or may not be published to.
In other words, it uses the RecordNameStrategy_.
The manager uses the combined Avro namespace and record name as the subject name.
The record name and namespace come from certain fields on an inner class named ``Meta``:

* ``schema_name``
* ``namespace``

.. code-block:: python
   :caption: Subject: my.namespace.mymodelcustom

   class MyModel(AvroBaseModel):
       str_field: str
       int_field: int

       class Meta:
           schema_name = "mymodel"
           namespace = "my.namespace"

If ``Meta.namespace`` is absent, then the avro record will have no namespace. You should always include it unless you have a very good reason not to, so that your record names won't conflict with any other record names in the schema registry. If ``Meta.schema_name`` is absent, then the class name will be used as the schema name, but it is good practice to explicitly define ``Meta.schema_name`` to avoid unintentionaly changing the schema_name and subject in the process of otherwise routine code refactoring.

.. _subject: https://docs.confluent.io/platform/current/schema-registry/fundamentals/index.html#schemas-subjects-and-topics
.. _RecordNameStrategy: https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html#sr-schemas-subject-name-strategy

Subject suffixes for development
================================

When you're developing and testing your app, you probably don't want to register new versions of its schemas in the subjects that actual deployed versions of the app are using.
You can instantiate the `~safir.kafka.PydanticSchemaManager` with a ``suffix`` argument to add that suffix onto all subjects used by the manager:

.. code-block:: python

   registry: AsyncSchemaRegistryClient
   manager = PydanticSchemaManager(registry=registry, suffix="_testing")

Or by using the helper:

.. code-block:: shell-session

   $ export SCHEMA_MANAGER_REGISTRY_URL=https://sasquatch-schema-registry.sasquatch:8081
   $ export SCHEMA_MANAGER_SUFFIX=_testing

.. code-block:: python

   from safir.kafka import SchemaManagerSettings

   config = SchemaManagerSettings()
   manager = config.make_manager()

Then the subjects are modified like this:

.. code-block:: python

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
