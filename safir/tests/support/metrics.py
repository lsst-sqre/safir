"""Helpers for app metrics testing."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta

from aiokafka.admin.client import NewTopic

from safir.metrics import EventsConfiguration, KafkaMetricsConfiguration
from safir.metrics._event_manager import KafkaEventManager

from .kafka import KafkaClients, KafkaStack

__all__ = ["MetricsStack", "make_metrics_stack"]


@dataclass
class MetricsStack:
    """Objects and external services in a full app metrics stack."""

    kafka_stack: KafkaStack
    """Kafka containers and connection info."""

    kafka_clients: KafkaClients
    """Kafka clients that point at the Kafka stack."""

    kafka_max_batch_size: int
    """The maximum number of messages to allow in an aiokafka produce batch.

    If another message is published while there are this many messages in the
    batch, aoikafka will block to send the batch.
    """

    event_manager: KafkaEventManager
    """An uninialized Kafka event manager."""

    metrics_config: KafkaMetricsConfiguration
    """Metrics configuration for all of the services in the stack."""


@asynccontextmanager
async def make_metrics_stack(
    *,
    kafka_stack: KafkaStack,
    kafka_clients: KafkaClients,
    kafka_max_batch_size: int = 16384,
) -> AsyncGenerator[MetricsStack]:
    """Yield a full metrics stack with underlying infrastructure.

    Parameters
    ----------
    kafka_stack
        A bucket of containers.
    kafka_clients
        A bucket of clients that point at those containers.
    kafka_max_batch_size
        The maximum number of messages to allow in an aiokafka produce batch.
        If another message is published while there are this many messages in
        the batch, aoikafka will block to send the batch.
    """
    config = KafkaMetricsConfiguration(
        application="testapp",
        enabled=True,
        events=EventsConfiguration(topic_prefix="what.ever"),
        kafka=kafka_stack.kafka_connection_settings,
        schema_manager=kafka_stack.schema_manager_settings,
        # This should be longer than it takes to restart the Kafka
        # container in a test. We're going to fake time in the test so we
        # can advance it quickly
        backoff_interval=timedelta(hours=1),
        raise_on_error=False,
    )

    manager = config.make_manager(
        extra_broker_settings={
            "max_batch_size": kafka_max_batch_size,
        }
    )
    try:
        topic = NewTopic(
            name="what.ever.testapp",
            num_partitions=1,
            replication_factor=1,
        )
        await kafka_clients.kafka_admin_client.create_topics([topic])

        await manager.initialize()

        yield MetricsStack(
            kafka_stack=kafka_stack,
            kafka_clients=kafka_clients,
            kafka_max_batch_size=kafka_max_batch_size,
            event_manager=manager,
            metrics_config=config,
        )
    finally:
        await manager.aclose()
