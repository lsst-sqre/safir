##################
Testing with Kafka
##################

Although FastStream_ provides some testing support by mocking Kafka brokers, it's sometimes easier and sometimes more effective to test against actual Kafka and Confluent schema registry servers.
To support this, Safir provides Testcontainers_ classes that allow your test suite to start Kafka and a Confluent schema registry server.
Usually these classes are used in test fixtures.

The Kafka container is heavily inspired by the standard Testcontainers_ Kafka container but supports TLS and SASL, always uses KRaft, and has some other differences.

To use any of these containers, depend on ``safir[kafka,testcontainers]``.
(In other words, add ``testcontainers`` to your Safir dependency extras.)

Kafka test fixtures
===================

The most common use of `safir.testing.containers.FullKafkaContainer` is in fixtures such as the following:

.. code-block:: python

   from collections.abc import Iterator

   import pytest
   from safir.testing.containers import FullKafkaContainer
   from testcontainers.core.network import Network


   @pytest.fixture(scope="session")
   def kafka_docker_network() -> Iterator[Network]:
       with Network() as network:
           yield network


   @pytest.fixture(scope="session")
   def global_kafka_container(
       kafka_docker_network: Network,
   ) -> Iterator[FullKafkaContainer]:
       container = FullKafkaContainer()
       container.with_network(kafka_docker_network)
       container.with_network_aliases("kafka")
       with container as kafka:
           yield kafka


   @pytest.fixture
   def kafka_container(
       global_kafka_container: FullKafkaContainer,
   ) -> Iterator[FullKafkaContainer]:
       global_kafka_container.reset()
       yield global_kafka_container

The separate ``kafka_container`` fixture resets the contents of all topics before each test so that tests don't interfere with each other.

The network is created separately so that you can add a Confluent schema registry to the same network if needed.
See :ref:`testcontainers-schema-registry`.

Typically, you will want to add some additional fixtures to get the Kafka connection settings and, if desired, pre-created aiokafka_ or FastStream_ clients:

.. code-block:: python

   from collections.abc import AsyncGenerator

   import pytest
   from aiokafka import AIOKafkaConsumer
   from aiokafka.admin.client import AIOKafkaAdminClient
   from faststream.kafka import KafkaBroker
   from safir.kafka import KafkaConnectionSettings, SecurityProtocol


   @pytest.fixture
   def kafka_connection_settings(
       kafka_container: FullKafkaContainer,
   ) -> KafkaConnectionSettings:
       return KafkaConnectionSettings(
           bootstrap_servers=kafka_container.get_bootstrap_server(),
           security_protocol=SecurityProtocol.PLAINTEXT,
       )


   @pytest_asyncio.fixture
   async def kafka_consumer(
       kafka_connection_settings: KafkaConnectionSettings,
   ) -> AsyncGenerator[AIOKafkaConsumer]:
       consumer = AIOKafkaConsumer(
           **kafka_connection_settings.to_aiokafka_params(),
           client_id="pytest-consumer",
       )
       await consumer.start()
       yield consumer
       await consumer.stop()


   @pytest_asyncio.fixture
   async def kafka_broker(
       kafka_connection_settings: KafkaConnectionSettings,
   ) -> AsyncGenerator[KafkaBroker]:
       broker = KafkaBroker(
           **kafka_connection_settings.to_faststream_params(),
           client_id="pytest-broker",
       )
       await broker.start()
       yield broker
       await broker.stop()


   @pytest_asyncio.fixture
   async def kafka_admin_client(
       kafka_connection_settings: KafkaConnectionSettings,
   ) -> AsyncGenerator[AIOKafkaAdminClient]:
       client = AIOKafkaAdminClient(
           **kafka_connection_settings.to_aiokafka_params(),
           client_id="pytest-admin",
       )
       await client.start()
       yield client
       await client.close()

TLS authentication to Kafka
---------------------------

If you want to test TLS-authenticated connections to Kafka, you can modify the ``global_kafka_container`` fixture as follows to download the self-signed certificates from the container so that they can be used by clients.

.. note::

   Nearly all applications do not need to go to this additional work and can be tested with default plaintext connections as described above.
   This elaboration is only needed if you specifically need to test TLS or certificate authentication.

.. code-block:: python

   from pathlib import Path
   from collections.abc import Iterator

   import pytest
   from safir.testing.containers import FullKafkaContainer
   from testcontainers.core.network import Network


   @pytest.fixture(scope="session")
   def kafka_cert_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
       return tmp_path_factory.mktemp("kafka-certs")


   @pytest.fixture(scope="session")
   def global_kafka_container(
       kafka_docker_network: Network, kafka_cert_path: Path
   ) -> Iterator[FullKafkaContainer]:
       container = FullKafkaContainer()
       container.with_network(kafka_docker_network)
       container.with_network_aliases("kafka")
       with container as kafka:
           for filename in ("ca.crt", "client.crt", "client.key"):
               contents = container.get_secret_file_contents(filename)
               (kafka_cert_path / filename).write_text(contents)
           yield kafka

The Kafka client can then read the CA certificate, client certificate, and client key from the files in the directory provided by the ``kafka_cert_path`` fixture.
For example:

.. code-block:: python

   from pathlib import Path

   from safir.kafka import KafkaConnectionSettings, SecurityProtocol
   from safir.testing.containers import FullKafkaContainer


   async def test_ssl(
       kafka_cert_path: Path, kafka_container: FullKafkaContainer
   ) -> None:
       cluster_ca_path = kafka_cert_path / "ca.crt"
       client_cert_path = kafka_cert_path / "client.crt"
       client_key_path = kafka_cert_path / "client.key"

       bootstrap_server = kafka_container.get_ssl_bootstrap_server()
       settings = KafkaConnectionSettings(
           bootstrap_servers=bootstrap_server,
           security_protocol=SecurityProtocol.SSL,
           cluster_ca_path=cluster_ca_path,
           client_cert_path=client_cert_path,
           client_key_path=client_key_path,
       )

       # tests go here

.. _testcontainers-schema-registry:

Schema registry text fixtures
=============================

To additionally create a Confluent schema registry server that manages schema in the test Kafka container, use fixtures like the following:

.. code-block:: python

   from collections.abc import Iterator

   from testcontainers.core.network import Network
   from safir.testing.containers import SchemaRegistryContainer


   @pytest.fixture(scope="session")
   def global_schema_registry_container(
       global_kafka_container: FullKafkaContainer,
       kafka_docker_network: Network,
   ) -> Iterator[SchemaRegistryContainer]:
       container = SchemaRegistryContainer(network=kafka_docker_network)
       container.with_network(kafka_docker_network)
       container.with_network_aliases("schemaregistry")
       with container as schema_registry:
           yield schema_registry


   @pytest.fixture
   def schema_registry_container(
       global_schema_registry_container: SchemaRegistryContainer,
   ) -> Iterator[SchemaRegistryContainer]:
       global_schema_registry_container.reset()
       yield global_schema_registry_container

This uses the ``kafka_docker_network`` fixture so that the schema registry runs in the same network as Kafka.

As with the Kafka container, you will probably want additional fixtures to create a Safir configuration and a client:

.. code-block:: python

   import pytest
   from pydantic import AnyUrl
   from safir.testing.containers import SchemaRegistryContainer
   from safir.kafka import SchemaManagerSettings, PydanticSchemaManager


   @pytest.fixture
   def schema_manager_settings(
       schema_registry_container: SchemaRegistryContainer,
   ) -> SchemaManagerSettings:
       return SchemaManagerSettings(
           registry_url=AnyUrl(schema_registry_container.get_url())
       )


   @pytest.fixture
   def schema_manager(
       schema_manager_settings: SchemaManagerSettings,
   ) -> PydanticSchemaManager:
       return schema_manager_settings.make_manager()

The schema manager does not require authentication.
