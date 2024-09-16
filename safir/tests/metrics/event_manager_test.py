"""Test metrics tooling."""

import asyncio
import math
from uuid import UUID

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka.annotations import KafkaBroker
from pydantic import Field

from safir.kafka.config import KafkaConnectionSettings
from safir.metrics.config import MetricsConfiguration
from safir.metrics.dependencies import EventsDependency
from safir.metrics.event_manager import (
    EventManager,
    Publisher,
    create_event_manager_from_config,
)
from safir.metrics.models import EventMetadata, Payload
from safir.schema_manager.config import (
    SchemaManagerSettings,
    SchemaRegistryConnectionSettings,
)
from safir.schema_manager.pydantic_schema_manager import PydanticSchemaManager


class MyEvent(Payload):
    """An event payload."""

    foo: str


class Events:
    """A class to hold event publishers."""

    def __init__(self, manager: EventManager) -> None:
        self.my_event = manager.create_publisher(MyEvent)


async def subscribe_and_wait(consumer: AIOKafkaConsumer, pattern: str) -> None:
    """Avoid race condition when subscribing to topics.

    There is some race condition where an exception is raised if we start
    trying to consume messages too soon after we have subscribed to a topic
    or pattern, because partitions haven't been assigned to the consumer yet.
    """
    consumer.subscribe(pattern=pattern)
    await asyncio.sleep(0.5)


async def assert_from_kafka(
    consumer: AIOKafkaConsumer,
    manager: EventManager,
    event: Publisher[MyEvent],
    foo: str,
) -> None:
    """Grab a message from kafka, deserialize it, and assert stuff about it."""
    message = await consumer.getone()
    assert isinstance(message.value, bytes)
    deserialized = await manager._schema_manager.deserialize(
        message.value, event.event_class
    )

    assert isinstance(deserialized, EventMetadata)
    assert isinstance(deserialized.id, UUID)
    assert deserialized.service == "test-app"

    # dataclasses-avroschema serializes python ``datetime``s into avro
    # ``timestamp-millis``s
    assert (
        math.trunc(deserialized.timestamp_ns / 1e6)
        == deserialized.timestamp.timestamp() * 1e3
    )

    # Mypy can't deal with the fact that deserialized has both EventMetadata
    # AND MyEvent as bases, so let's pretend we don't know either :(
    # https://github.com/python/mypy/issues/12314
    assert getattr(deserialized, "foo", None) == foo


async def integration_test(
    *,
    kafka_broker: KafkaBroker | KafkaConnectionSettings,
    kafka_admin_client: AIOKafkaAdminClient | KafkaConnectionSettings,
    schema_manager: PydanticSchemaManager | SchemaManagerSettings,
    kafka_consumer: AIOKafkaConsumer,
) -> EventManager:
    """Publish events to actual storage and read them back and verify them."""
    config = MetricsConfiguration(
        service="test-app",
        base_topic_prefix="what.ever",
    )

    # Construct an event manager and intialize our events dependency
    manager = create_event_manager_from_config(config)

    # Create an events dependency and initialize it with the transport config
    events_dependency = EventsDependency(Events)
    await events_dependency.initialize(
        manager=manager,
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
    )

    # Publish events
    event = events_dependency.events.my_event
    await event.publish(MyEvent(foo="bar1"))
    await event.publish(MyEvent(foo="bar2"))
    await events_dependency.aclose()

    # Set up a kafka consumer
    expected_topic = "what.ever.test-app.MyEvent"
    await subscribe_and_wait(consumer=kafka_consumer, pattern=expected_topic)
    await kafka_consumer.seek_to_beginning()

    # Assert stuff
    assert event.topic == expected_topic
    await assert_from_kafka(kafka_consumer, manager, event, "bar1")
    await assert_from_kafka(kafka_consumer, manager, event, "bar2")

    return manager


@pytest.mark.asyncio
async def test_events_connection_info_integration(
    kafka_connection_settings: KafkaConnectionSettings,
    schema_registry_connection_settings: SchemaRegistryConnectionSettings,
    kafka_consumer: AIOKafkaConsumer,
) -> None:
    """Test all metrics-events-related stuff against real storage."""
    # Build our config models
    schema_manager_settings = SchemaManagerSettings(
        schema_registry=schema_registry_connection_settings
    )

    manager = await integration_test(
        kafka_broker=kafka_connection_settings,
        kafka_admin_client=kafka_connection_settings,
        schema_manager=schema_manager_settings,
        kafka_consumer=kafka_consumer,
    )

    # If we give connection config instead of clients to the manager, it should
    # clean up all of the clients it creates
    assert manager._admin_client._closed
    assert not await manager._broker.ping(timeout=1)


@pytest.mark.asyncio
async def test_events_clients_integration(
    kafka_broker: KafkaBroker,
    kafka_admin_client: AIOKafkaAdminClient,
    schema_manager: PydanticSchemaManager,
    kafka_consumer: AIOKafkaConsumer,
) -> None:
    """Test all metrics-events-related stuff against real storage."""
    await integration_test(
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
        kafka_consumer=kafka_consumer,
    )

    # If we give clients instead of connection config to the manager, it should
    # NOT clean up the clients we pass in
    assert not kafka_admin_client._closed
    assert await kafka_broker.ping(timeout=1)


@pytest.mark.asyncio
async def test_noop() -> None:
    """Test that no-op actually does no operations."""
    config = MetricsConfiguration(
        service="test-app",
        base_topic_prefix="what.ever",
        noop=True,
    )
    manager = create_event_manager_from_config(config)

    event = manager.create_publisher(MyEvent)
    await manager.register_events(
        kafka_broker=None,
        kafka_admin_client=None,
        schema_manager=None,
    )

    await event.publish(MyEvent(foo="bar1"))
    await event.publish(MyEvent(foo="bar2"))
    await manager.aclose()

    topic = "what.ever.test-app.MyEvent"
    assert event.topic == topic


def test_invalid_payload() -> None:
    config = MetricsConfiguration(
        service="test-app",
        base_topic_prefix="what.ever",
        noop=True,
    )
    manager = create_event_manager_from_config(config)

    class MyInvalidEvent(Payload):
        good_field: str = Field()
        bad_field: list[str] = Field()
        another_bad_field: dict[str, str] = Field()

    with pytest.raises(ValueError, match="Unsupported Avro Schema") as excinfo:
        manager.create_publisher(MyInvalidEvent)
    err = str(excinfo.value)

    assert "bad_field" in err
    assert "another_bad_field" in err
    assert "good_field" not in err
