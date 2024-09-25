"""Test metrics tooling."""

import asyncio
import math
from uuid import UUID

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from faststream.kafka import KafkaBroker
from pydantic import AnyUrl, Field
from schema_registry.client.client import AsyncSchemaRegistryClient
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)

from safir.kafka import (
    KafkaConnectionSettings,
    PydanticSchemaManager,
    SchemaManagerSettings,
    SecurityProtocol,
)
from safir.metrics import (
    EventDependency,
    EventManager,
    EventMetadata,
    EventPayload,
    EventPublisher,
    MetricsConfiguration,
    MetricsConfigurationWithKafka,
)
from safir.metrics._exceptions import (
    CreateAfterRegisterError,
    DuplicateEventError,
    KafkaTopicError,
)


class MyEvent(EventPayload):
    """An event payload."""

    foo: str


class Events:
    """A class to hold event publishers."""

    def __init__(self, manager: EventManager) -> None:
        self.my_event = manager.create_publisher("myevent", MyEvent)


def dummy_manager(*, noop: bool = False) -> EventManager:
    "Create a manager with bunk kafka creds."
    config = MetricsConfigurationWithKafka(
        metrics_events=MetricsConfiguration(
            app_name="testapp", topic_prefix="what.ever", noop=noop
        ),
        kafka=KafkaConnectionSettings(
            bootstrap_servers="whatever",
            security_protocol=SecurityProtocol.PLAINTEXT,
        ),
        schema_manager=SchemaManagerSettings(
            registry_url=AnyUrl("http://whatever.code")
        ),
    )
    return config.make_manager()


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
) -> None:
    """Grab a message from kafka, deserialize it, and assert stuff about it."""
    message = await consumer.getone()
    assert isinstance(message.value, bytes)
    serializer = AsyncAvroMessageSerializer(schema_registry)
    deserialized_dict = await serializer.decode_message(message.value)
    assert deserialized_dict is not None
    deserialized = event.event_class(**deserialized_dict)

    assert isinstance(deserialized, EventMetadata)
    assert isinstance(deserialized.id, UUID)
    assert deserialized.app_name == "testapp"

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

    # Create an events dependency and initialize it with the transport config
    events_dependency = EventDependency(Events)
    await events_dependency.initialize(manager=manager)

    # Publish events
    event = events_dependency.events.my_event
    await event.publish(MyEvent(foo="bar1"))
    await event.publish(MyEvent(foo="bar2"))
    await events_dependency.aclose()

    # Set up a kafka consumer
    expected_topic = "what.ever.testapp"
    await subscribe_and_wait(consumer=kafka_consumer, pattern=expected_topic)
    await kafka_consumer.seek_to_beginning()

    # Assert stuff
    assert event.publisher.topic == expected_topic
    await assert_from_kafka(kafka_consumer, schema_registry, event, "bar1")
    await assert_from_kafka(kafka_consumer, schema_registry, event, "bar2")

    await manager.aclose()


@pytest.mark.asyncio
async def test_managed_storage(
    kafka_connection_settings: KafkaConnectionSettings,
    schema_manager_settings: SchemaManagerSettings,
    kafka_consumer: AIOKafkaConsumer,
    kafka_admin_client: AIOKafkaAdminClient,
) -> None:
    """Publish events to actual storage and read them back and verify them."""
    config = MetricsConfigurationWithKafka(
        metrics_events=MetricsConfiguration(
            app_name="testapp",
            topic_prefix="what.ever",
        ),
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
    manager = EventManager(
        app_name="testapp",
        base_topic_prefix="what.ever",
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
        manage_kafka=False,
        noop=False,
    )
    await integration_test(
        manager, schema_manager_settings, kafka_consumer, kafka_admin_client
    )

    # Make sure storage is NOT cleaned up
    assert not manager._admin_client._closed
    assert await manager._broker.ping(timeout=1)


@pytest.mark.asyncio
async def test_topic_not_created(
    schema_manager_settings: SchemaManagerSettings,
    kafka_consumer: AIOKafkaConsumer,
    kafka_broker: KafkaBroker,
    kafka_admin_client: AIOKafkaAdminClient,
    schema_manager: PydanticSchemaManager,
) -> None:
    manager = EventManager(
        app_name="testapp",
        base_topic_prefix="what.ever",
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
        manage_kafka=False,
        noop=False,
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
async def test_create_after_register(
    schema_manager_settings: SchemaManagerSettings,
    kafka_consumer: AIOKafkaConsumer,
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

    manager = EventManager(
        app_name="testapp",
        base_topic_prefix="what.ever",
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
        manage_kafka=False,
        noop=False,
    )

    class MyOtherEvent(EventPayload):
        blah: int

    manager.create_publisher("myevent", MyEvent)
    await manager.register_and_initialize()

    with pytest.raises(CreateAfterRegisterError):
        await integration_test(
            manager,
            schema_manager_settings,
            kafka_consumer,
            kafka_admin_client,
        )
        manager.create_publisher("myotherevent", MyOtherEvent)


@pytest.mark.asyncio
async def test_duplicate_event() -> None:
    class MyOtherEvent(EventPayload):
        blah: int

    manager = dummy_manager()
    manager.create_publisher("myevent", MyEvent)
    with pytest.raises(DuplicateEventError):
        manager.create_publisher("myevent", MyOtherEvent)


@pytest.mark.asyncio
async def test_invalid_payload() -> None:
    manager = dummy_manager()

    class MyInvalidEvent(EventPayload):
        good_field: str = Field()
        bad_field: list[str] = Field()
        another_bad_field: dict[str, str] = Field()

    with pytest.raises(ValueError, match="Unsupported Avro Schema") as excinfo:
        manager.create_publisher("myinvalidevent", MyInvalidEvent)
    err = str(excinfo.value)

    assert "bad_field" in err
    assert "another_bad_field" in err
    assert "good_field" not in err


@pytest.mark.asyncio
async def test_noop() -> None:
    manager = dummy_manager(noop=True)

    event = manager.create_publisher("myevent", MyEvent)
    await manager.register_and_initialize()

    await event.publish(MyEvent(foo="bar1"))
    await event.publish(MyEvent(foo="bar2"))
    await manager.aclose()

    topic = "what.ever.testapp"
    assert event.publisher.topic == topic
