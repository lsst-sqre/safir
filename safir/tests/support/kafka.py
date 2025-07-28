"""Support for testing Kafka helpers."""

import logging
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path

from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient
from docker.errors import NotFound
from faststream.kafka import KafkaBroker
from pydantic import AnyUrl
from schema_registry.client import AsyncSchemaRegistryClient
from testcontainers.core.network import Network

from safir.kafka import (
    KafkaConnectionSettings,
    SchemaManagerSettings,
    SecurityProtocol,
)
from safir.kafka._manager import PydanticSchemaManager
from safir.testing.containers import (
    FullKafkaContainer,
    SchemaRegistryContainer,
)

__all__ = [
    "KafkaClients",
    "KafkaStack",
    "make_kafka_clients",
    "make_kafka_stack",
]


@dataclass
class KafkaStack:
    """Objects and external services in a full app metrics stack."""

    kafka_container: FullKafkaContainer
    """A Kafka docker TestContainer."""

    kafka_cert_path: Path
    """The local path containing the Kafka certs."""

    schema_registry_container: SchemaRegistryContainer
    """A schema registry TestContainer."""

    kafka_connection_settings: KafkaConnectionSettings
    """Connection settings for the Kafka container."""

    schema_manager_settings: SchemaManagerSettings
    """Settings for a schema manager pointed at the stack."""


@dataclass
class KafkaClients:
    """Clients for pieces of the Kafka stack."""

    kafka_consumer: AIOKafkaConsumer
    """An AIOKafkaConsumer pointed at the stack."""

    kafka_broker: KafkaBroker
    """A faststream KafkaBroker pointed at the stack."""

    kafka_admin_client: AIOKafkaAdminClient
    """An AIOKafkaAdminClient pointed at the stack."""

    schema_registry_client: AsyncSchemaRegistryClient
    """A schema registry client pointed at the stack."""

    schema_manager: PydanticSchemaManager
    """A PydanticSchemaManager pointed at the stack."""


@contextmanager
def make_kafka_stack(
    kafka_cert_path: Path, *, constant_host_ports: bool = False
) -> Generator[KafkaStack]:
    """Yield a full kafka stack with clients and underlying infrastructure.

    Parameters
    ----------
    kafka_cert_path
        The local path to Kafka cert files. Probably comes from a
        tmp_path_factory fixture.
    constant_host_ports
        Whether or not the Kafka container should use explicitly numbered host
        ports. This is needed for tests that stop and restart the Kafka
        container so that it comes back up with the same mapped host ports.
    """
    kafka_container = None
    schema_registry_container = None
    network = None
    try:
        network = Network().create()
        kafka_container = FullKafkaContainer(
            constant_host_ports=constant_host_ports
        )
        kafka_container.with_network(network)
        kafka_container.with_network_aliases("kafka")

        kafka_container.start()

        for filename in ("ca.crt", "client.crt", "client.key"):
            contents = kafka_container.get_secret_file_contents(filename)
            (kafka_cert_path / filename).write_text(contents)

        kafka_connection_settings = KafkaConnectionSettings(
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            security_protocol=SecurityProtocol.PLAINTEXT,
        )
        schema_registry_container = SchemaRegistryContainer(network=network)
        schema_registry_container.with_network(network)
        schema_registry_container.with_network_aliases("schemaregistry")

        schema_registry_container.start()

        schema_manager_settings = SchemaManagerSettings(
            registry_url=AnyUrl(schema_registry_container.get_url())
        )

        yield KafkaStack(
            kafka_container=kafka_container,
            kafka_cert_path=kafka_cert_path,
            schema_registry_container=schema_registry_container,
            kafka_connection_settings=kafka_connection_settings,
            schema_manager_settings=schema_manager_settings,
        )

    finally:
        if kafka_container:
            try:
                kafka_container.stop()
            except NotFound:
                logging.getLogger().info(
                    "Trying to stop Kafka container, but it doesn't exist."
                    " This is fine if the container was stopped in the test"
                    " itself."
                )

        if schema_registry_container:
            try:
                schema_registry_container.stop()
            except NotFound:
                logging.getLogger().info(
                    "Trying to stop Schema Registry container, but it doesn't"
                    " exist. This is fine if the container was stopped in the"
                    " test itself."
                )
        if network:
            network.remove()


@asynccontextmanager
async def make_kafka_clients(
    stack: KafkaStack,
) -> AsyncGenerator[KafkaClients]:
    """Yield a bucket of useful Kafka and schema manager clients.

    Parameters
    ----------
    stack
        The containers to point the clients at.
    """
    kafka_consumer = None
    kafka_broker = None
    kafka_admin_client = None

    try:
        schema_registry_client = AsyncSchemaRegistryClient(
            **stack.schema_manager_settings.to_registry_params()
        )

        kafka_consumer = AIOKafkaConsumer(
            **stack.kafka_connection_settings.to_aiokafka_params(),
            client_id="pytest-consumer",
        )
        await kafka_consumer.start()

        kafka_broker = KafkaBroker(
            **stack.kafka_connection_settings.to_faststream_params(),
            client_id="pytest-broker",
        )
        await kafka_broker.start()

        kafka_admin_client = AIOKafkaAdminClient(
            **stack.kafka_connection_settings.to_aiokafka_params(),
            client_id="pytest-admin",
        )
        await kafka_admin_client.start()

        schema_manager = stack.schema_manager_settings.make_manager()

        yield KafkaClients(
            schema_registry_client=schema_registry_client,
            kafka_consumer=kafka_consumer,
            kafka_broker=kafka_broker,
            kafka_admin_client=kafka_admin_client,
            schema_manager=schema_manager,
        )
    finally:
        if kafka_consumer:
            await kafka_consumer.stop()
        if kafka_broker:
            await kafka_broker.stop()
        if kafka_admin_client:
            await kafka_admin_client.close()
