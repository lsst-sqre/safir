"""Test metrics tooling."""

from __future__ import annotations

import asyncio
import math
from datetime import timedelta
from enum import Enum
from typing import cast
from uuid import UUID

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from dataclasses_avroschema.pydantic import AvroBaseModel
from faststream.kafka import KafkaBroker
from pydantic import Field
from schema_registry.client.client import AsyncSchemaRegistryClient
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)

from safir.dependencies.metrics import EventDependency, EventMaker
from safir.kafka import (
    KafkaConnectionSettings,
    PydanticSchemaManager,
    SchemaManagerSettings,
)
from safir.metrics import (
    DisabledMetricsConfiguration,
    DuplicateEventError,
    EventManager,
    EventManagerUnintializedError,
    EventMetadata,
    EventPayload,
    EventPublisher,
    EventsConfiguration,
    KafkaEventManager,
    KafkaEventPublisher,
    KafkaMetricsConfiguration,
    KafkaTopicError,
)


class MyEvent(EventPayload):
    """An event payload."""

    foo: str
    duration: timedelta
    duration_union: timedelta | None


class Events(EventMaker):
    """A class to hold event publishers."""

    async def initialize(self, manager: EventManager) -> None:
        self.my_event = await manager.create_publisher("myevent", MyEvent)


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
    schema_registry: AsyncSchemaRegistryClient,
    event: EventPublisher[MyEvent],
    foo: str,
    duration: timedelta,
) -> None:
    """Grab a message from kafka, deserialize it, and assert stuff about it."""
    message = await consumer.getone()
    assert isinstance(message.value, bytes)
    serializer = AsyncAvroMessageSerializer(schema_registry)
    deserialized_dict = await serializer.decode_message(message.value)
    assert deserialized_dict is not None
    event_class = cast("type[AvroBaseModel]", event._event_class)
    deserialized = event_class(**deserialized_dict)

    assert isinstance(deserialized, EventMetadata)
    assert isinstance(deserialized.id, UUID)
    assert deserialized.application == "testapp"

    # dataclasses-avroschema serializes python datetime's into avro
    # timestamp-millis's
    deserialized_ms = math.trunc(deserialized.timestamp_ns / 1e6)
    assert deserialized_ms == deserialized.timestamp.timestamp() * 1e3

    # Mypy can't deal with the fact that deserialized has both EventMetadata
    # AND MyEvent as bases, so let's pretend we don't know either :(
    # https://github.com/python/mypy/issues/12314
    assert getattr(deserialized, "foo", None) == foo
    assert getattr(deserialized, "duration", None) == duration


async def integration_test(
    manager: EventManager,
    schema_manager_settings: SchemaManagerSettings,
    kafka_consumer: AIOKafkaConsumer,
    kafka_admin_client: AIOKafkaAdminClient,
    *,
    create_topic: bool = True,
) -> None:
    """Test the interaction of the EventManager and the EventsDependency."""
    schema_registry = AsyncSchemaRegistryClient(
        **schema_manager_settings.to_registry_params()
    )

    if create_topic:
        topic = NewTopic(
            name="what.ever.testapp",
            num_partitions=1,
            replication_factor=1,
        )
        await kafka_admin_client.create_topics([topic])

    # Initialize the event manager
    await manager.initialize()

    # Create an events dependency and initialize it with the transport config
    events_dependency = EventDependency(Events())
    await events_dependency.initialize(manager=manager)

    # Publish events
    event = events_dependency.events.my_event
    await event.publish(
        MyEvent(
            foo="bar1",
            duration=timedelta(seconds=2, milliseconds=123),
            duration_union=None,
        )
    )
    published = await event.publish(
        MyEvent(
            foo="bar2",
            duration=timedelta(seconds=2, milliseconds=456),
            duration_union=None,
        )
    )
    schema = published.avro_schema_to_python()
    assert schema["name"] == "myevent"
    assert schema["namespace"] == "what.ever.testapp"

    # Set up a kafka consumer
    expected_topic = "what.ever.testapp"
    await subscribe_and_wait(consumer=kafka_consumer, pattern=expected_topic)
    await kafka_consumer.seek_to_beginning()

    # Assert stuff
    assert isinstance(event, KafkaEventPublisher)
    assert event._publisher.topic == expected_topic
    await assert_from_kafka(
        kafka_consumer,
        schema_registry,
        event,
        "bar1",
        timedelta(seconds=2.123),
    )
    await assert_from_kafka(
        kafka_consumer,
        schema_registry,
        event,
        "bar2",
        timedelta(seconds=2.456),
    )

    await manager.aclose()


@pytest.mark.asyncio
async def test_managed_storage(
    kafka_connection_settings: KafkaConnectionSettings,
    schema_manager_settings: SchemaManagerSettings,
    kafka_consumer: AIOKafkaConsumer,
    kafka_admin_client: AIOKafkaAdminClient,
) -> None:
    """Publish events to actual storage and read them back and verify them."""
    config = KafkaMetricsConfiguration(
        application="testapp",
        events=EventsConfiguration(topic_prefix="what.ever"),
        kafka=kafka_connection_settings,
        schema_manager=schema_manager_settings,
    )

    # Construct an event manager and intialize our events dependency
    manager = config.make_manager()
    await integration_test(
        manager, schema_manager_settings, kafka_consumer, kafka_admin_client
    )

    # Make sure storage is cleaned up
    assert manager._admin_client._closed
    assert not await manager._broker.ping(timeout=1)


@pytest.mark.asyncio
async def test_unmanaged_storage(
    schema_manager_settings: SchemaManagerSettings,
    kafka_consumer: AIOKafkaConsumer,
    kafka_broker: KafkaBroker,
    kafka_admin_client: AIOKafkaAdminClient,
    schema_manager: PydanticSchemaManager,
) -> None:
    """Publish events to actual storage and read them back and verify them."""
    manager = KafkaEventManager(
        application="testapp",
        topic_prefix="what.ever",
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
        manage_kafka_broker=False,
    )
    await integration_test(
        manager, schema_manager_settings, kafka_consumer, kafka_admin_client
    )

    # Make sure storage is NOT cleaned up
    assert await manager._broker.ping(timeout=1)


@pytest.mark.asyncio
async def test_topic_not_created(
    schema_manager_settings: SchemaManagerSettings,
    kafka_consumer: AIOKafkaConsumer,
    kafka_broker: KafkaBroker,
    kafka_admin_client: AIOKafkaAdminClient,
    schema_manager: PydanticSchemaManager,
) -> None:
    manager = KafkaEventManager(
        application="testapp",
        topic_prefix="what.ever",
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
        manage_kafka_broker=False,
    )

    with pytest.raises(KafkaTopicError):
        await integration_test(
            manager,
            schema_manager_settings,
            kafka_consumer,
            kafka_admin_client,
            create_topic=False,
        )


@pytest.mark.asyncio
async def test_create_before_initialize(
    kafka_broker: KafkaBroker,
    kafka_admin_client: AIOKafkaAdminClient,
    schema_manager: PydanticSchemaManager,
) -> None:
    topic = NewTopic(
        name="what.ever.testapp",
        num_partitions=1,
        replication_factor=1,
    )
    await kafka_admin_client.create_topics([topic])

    manager = KafkaEventManager(
        application="testapp",
        topic_prefix="what.ever",
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
        manage_kafka_broker=False,
    )

    with pytest.raises(EventManagerUnintializedError):
        await manager.create_publisher("myevent", MyEvent)


@pytest.mark.asyncio
async def test_duplicate_event(event_manager: EventManager) -> None:
    class MyOtherEvent(EventPayload):
        blah: int

    await event_manager.create_publisher("myevent", MyEvent)
    with pytest.raises(DuplicateEventError):
        await event_manager.create_publisher("myevent", MyOtherEvent)


@pytest.mark.asyncio
async def test_invalid_payload(event_manager: EventManager) -> None:
    class MyEnum(Enum):
        case1 = "case1"
        case2 = "case2"

    class MyInvalidEvent(EventPayload):
        good_simple_field: str = Field()
        good_union_field: str | None = Field()
        good_enum_field: MyEnum = Field()
        bad_list_field: list[str] = Field()
        bad_union_field: dict[str, str] | None = Field()
        bad_dict_field: dict[str, str] = Field()

    with pytest.raises(ValueError, match="Unsupported Avro Schema") as excinfo:
        await event_manager.create_publisher("myinvalidevent", MyInvalidEvent)
    err = str(excinfo.value)

    assert "bad_list_field" in err
    assert "bad_union_field" in err
    assert "bad_dict_field" in err

    assert "good_simple_field" not in err
    assert "good_union_field" not in err
    assert "good_enum_field" not in err


@pytest.mark.asyncio
async def test_disable() -> None:
    config = DisabledMetricsConfiguration(
        enabled=False,
        application="testapp",
        events=EventsConfiguration(topic_prefix="what.ever"),
    )
    manager = config.make_manager()

    await manager.initialize()
    event = await manager.create_publisher("myevent", MyEvent)

    await event.publish(
        MyEvent(foo="bar1", duration=timedelta(seconds=1), duration_union=None)
    )
    await event.publish(
        MyEvent(foo="bar2", duration=timedelta(seconds=1), duration_union=None)
    )
    await manager.aclose()
