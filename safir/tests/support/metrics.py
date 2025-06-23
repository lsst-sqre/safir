"""Helpers for app metrics testing."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from aiokafka.admin.client import NewTopic
from docker.errors import NotFound
from pydantic import AnyUrl
from schema_registry.client import AsyncSchemaRegistryClient
from testcontainers.core.network import Network

from safir.kafka import (
    KafkaConnectionSettings,
    SchemaManagerSettings,
    SecurityProtocol,
)
from safir.metrics import EventsConfiguration, KafkaMetricsConfiguration
from safir.metrics._event_manager import KafkaEventManager
from safir.testing.containers import (
    FullKafkaContainer,
    SchemaRegistryContainer,
)

__all__ = ["MetricsStack", "metrics_stack"]


@dataclass
class MetricsStack:
    """Objects and external services in a full app metrics stack."""

    event_manager: KafkaEventManager
    kafka_container: FullKafkaContainer
    kafka_connection_settings: KafkaConnectionSettings
    schema_registry_client: AsyncSchemaRegistryClient
    max_batch_size: int
    metrics_config: KafkaMetricsConfiguration


@asynccontextmanager
async def metrics_stack(
    tmp_path: Path,
) -> AsyncGenerator[MetricsStack]:
    """Yield a full metrics stack with underlying infrastructure."""
    cert_path = tmp_path / "kafka-certs"
    cert_path.mkdir()

    # We want to set this as log as possible so we can trigger an exception in
    # the EventManager publish method. This only happens when we send messages
    # at such a rate that a batch fills up before aiokafka can send it in the
    # background.
    max_batch_size = 1

    with Network() as network:
        kafka_container = FullKafkaContainer(constant_host_ports=True)
        kafka_container.with_network(network)
        kafka_container.with_network_aliases("kafka")

        kafka_container.start()

        for filename in ("ca.crt", "client.crt", "client.key"):
            contents = kafka_container.get_secret_file_contents(filename)
            (cert_path / filename).write_text(contents)

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
        config = KafkaMetricsConfiguration(
            application="testapp",
            enabled=True,
            events=EventsConfiguration(topic_prefix="what.ever"),
            kafka=kafka_connection_settings,
            schema_manager=schema_manager_settings,
            # This should be longer than it takes to restart the Kafka
            # container in a test. We're going to fake time in the test so we
            # can advance it quickly
            backoff_interval=timedelta(hours=1),
        )

        manager = config.make_manager(
            extra_broker_settings={
                "max_batch_size": max_batch_size,
            }
        )
        await manager.initialize()
        topic = NewTopic(
            name="what.ever.testapp",
            num_partitions=1,
            replication_factor=1,
        )
        await manager._admin_client.create_topics([topic])

        schema_registry_client = AsyncSchemaRegistryClient(
            **schema_manager_settings.to_registry_params()
        )

        yield MetricsStack(
            event_manager=manager,
            kafka_container=kafka_container,
            kafka_connection_settings=kafka_connection_settings,
            schema_registry_client=schema_registry_client,
            max_batch_size=max_batch_size,
            metrics_config=config,
        )
        await manager.aclose()

        try:
            kafka_container.stop()
        except NotFound:
            logging.getLogger().info(
                "Trying to stop Kafka container, but it doesn't exist. This is"
                " fine if the container was stopped in the test itself."
            )

        try:
            schema_registry_container.stop()
        except NotFound:
            logging.getLogger().info(
                "Trying to stop Schema Registry container, but it doesn't"
                " exist. This is fine if the container was stopped in the test"
                " itself."
            )
