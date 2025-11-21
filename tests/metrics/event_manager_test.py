"""Test metrics tooling."""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import cast
from uuid import UUID

import pytest
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import KafkaConnectionError
from dataclasses_avroschema.pydantic import AvroBaseModel
from faststream.kafka.publisher.producer import AioKafkaFastProducer
from pydantic import Field, HttpUrl
from schema_registry.client.client import AsyncSchemaRegistryClient
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)
from structlog.testing import LogCapture
from time_machine import TimeMachineFixture

from safir.dependencies.metrics import EventDependency, EventMaker
from safir.kafka import (
    KafkaConnectionSettings,
    SchemaManagerSettings,
    SecurityProtocol,
)
from safir.metrics import (
    DisabledMetricsConfiguration,
    DuplicateEventError,
    EventManager,
    EventManagerUninitializedError,
    EventMetadata,
    EventPayload,
    EventPublisher,
    EventsConfiguration,
    KafkaEventManager,
    KafkaEventPublisher,
    KafkaMetricsConfiguration,
    KafkaTopicError,
)
from safir.metrics._exceptions import UnsupportedAvroSchemaError
from tests.support.kafka import KafkaClients, KafkaStack

from ..support.metrics import MetricsStack


class MyEvent(EventPayload):
    """An event payload."""

    foo: str
    duration: timedelta
    duration_union: timedelta | None


class MyOtherEvent(EventPayload):
    """An event payload."""

    bar: str
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


async def flush_producer(manager: KafkaEventManager) -> None:
    """Hack the type system to flush the underlying aiokafka producer."""
    assert manager._broker._producer
    producer = cast("AioKafkaFastProducer", manager._broker._producer)
    await producer.flush()


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
    # timestamp-millis's. The timestamp_ns and the timestamp fields could
    # differ by a millisecond due to differences between time.time_ns and the
    # passing of datetime objects through the dataclasses-avroschema
    # serialization and deserialization.
    deserialized_ms = math.trunc(deserialized.timestamp_ns / 1e6)
    timestamp_ms = deserialized.timestamp.timestamp() * 1e3
    difference = abs(deserialized_ms - timestamp_ms)
    assert difference <= 1

    # Mypy can't deal with the fact that deserialized has both EventMetadata
    # AND MyEvent as bases, so let's pretend we don't know either :(
    # https://github.com/python/mypy/issues/12314
    assert getattr(deserialized, "foo", None) == foo
    assert getattr(deserialized, "duration", None) == duration


async def integration_test(
    manager: EventManager,
    schema_registry_client: AsyncSchemaRegistryClient,
    kafka_consumer: AIOKafkaConsumer,
    kafka_admin_client: AIOKafkaAdminClient,
    *,
    create_topic: bool = True,
) -> None:
    """Test the interaction of the EventManager and the EventsDependency."""
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
        schema_registry_client,
        event,
        "bar1",
        timedelta(seconds=2.123),
    )
    await assert_from_kafka(
        kafka_consumer,
        schema_registry_client,
        event,
        "bar2",
        timedelta(seconds=2.456),
    )

    await manager.aclose()


@pytest.mark.asyncio
async def test_managed_storage(
    kafka_stack: KafkaStack,
    kafka_clients: KafkaClients,
) -> None:
    """Publish events to actual storage and read them back and verify them."""
    config = KafkaMetricsConfiguration(
        application="testapp",
        events=EventsConfiguration(topic_prefix="what.ever"),
        kafka=kafka_stack.kafka_connection_settings,
        schema_manager=kafka_stack.schema_manager_settings,
    )

    # Construct an event manager and intialize our events dependency
    manager = config.make_manager()
    await integration_test(
        manager,
        kafka_clients.schema_registry_client,
        kafka_clients.kafka_consumer,
        kafka_clients.kafka_admin_client,
    )

    # Make sure storage is cleaned up
    assert manager._admin_client._closed
    assert not await manager._broker.ping(timeout=1)


@pytest.mark.asyncio
async def test_unmanaged_storage(
    kafka_clients: KafkaClients,
) -> None:
    """Publish events to actual storage and read them back and verify them."""
    manager = KafkaEventManager(
        application="testapp",
        topic_prefix="what.ever",
        kafka_broker=kafka_clients.kafka_broker,
        kafka_admin_client=kafka_clients.kafka_admin_client,
        schema_manager=kafka_clients.schema_manager,
        manage_kafka_broker=False,
    )
    await integration_test(
        manager,
        kafka_clients.schema_registry_client,
        kafka_clients.kafka_consumer,
        kafka_clients.kafka_admin_client,
    )

    # Make sure storage is NOT cleaned up
    assert await manager._broker.ping(timeout=1)


@pytest.mark.asyncio
async def test_topic_not_created(
    kafka_clients: KafkaClients,
) -> None:
    kafka_broker = kafka_clients.kafka_broker
    kafka_consumer = kafka_clients.kafka_consumer
    kafka_admin_client = kafka_clients.kafka_admin_client
    schema_registry_client = kafka_clients.schema_registry_client
    schema_manager = kafka_clients.schema_manager

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
            schema_registry_client,
            kafka_consumer,
            kafka_admin_client,
            create_topic=False,
        )


@pytest.mark.asyncio
async def test_create_before_initialize(
    kafka_clients: KafkaClients,
) -> None:
    kafka_admin_client = kafka_clients.kafka_admin_client
    kafka_broker = kafka_clients.kafka_broker
    schema_manager = kafka_clients.schema_manager

    manager = KafkaEventManager(
        application="testapp",
        topic_prefix="what.ever",
        kafka_broker=kafka_broker,
        kafka_admin_client=kafka_admin_client,
        schema_manager=schema_manager,
        manage_kafka_broker=False,
    )

    with pytest.raises(EventManagerUninitializedError):
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

    with pytest.raises(UnsupportedAvroSchemaError) as excinfo:
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


@pytest.mark.asyncio
async def test_bad_kafka_from_start_no_raises(
    log_output: LogCapture,
    time_machine: TimeMachineFixture,
) -> None:
    # This has to be long enough so that we won't exhaust it naturally during
    # the execution of the test.
    backoff_interval = timedelta(hours=1)

    bad_kafka_settings = KafkaConnectionSettings(
        bootstrap_servers="nope:1234,nada:5678",
        security_protocol=SecurityProtocol.PLAINTEXT,
    )

    bad_schema_manager_settings = SchemaManagerSettings(
        registry_url=HttpUrl("https://nope.com")
    )
    config = KafkaMetricsConfiguration(
        application="testapp",
        enabled=True,
        events=EventsConfiguration(topic_prefix="what.ever"),
        kafka=bad_kafka_settings,
        schema_manager=bad_schema_manager_settings,
        backoff_interval=backoff_interval,
    )

    manager = config.make_manager()

    await manager.initialize()

    # Create an events dependency
    events_dependency = EventDependency(Events())
    await events_dependency.initialize(manager=manager)

    # Publish events, nothing should blow up
    event = events_dependency.events.my_event
    await event.publish(
        MyEvent(
            foo="bar1",
            duration=timedelta(seconds=2, milliseconds=123),
            duration_union=None,
        )
    )
    await event.publish(
        MyEvent(
            foo="bar2",
            duration=timedelta(seconds=2, milliseconds=456),
            duration_union=None,
        )
    )

    await manager.aclose()

    # We should have logged one publish error
    error_logs = [
        entry
        for entry in log_output.entries
        if entry.get("attempted_operation") == "publish"
    ]

    # Move time to after the backoff window. This isn't EXACTLY when the
    # backoff interval expires, but it's close enough for testing.
    time_machine.move_to(datetime.now(tz=UTC) + backoff_interval, tick=True)

    await event.publish(
        MyEvent(
            foo="bar3",
            duration=timedelta(seconds=2, milliseconds=123),
            duration_union=None,
        )
    )
    await event.publish(
        MyEvent(
            foo="bar4",
            duration=timedelta(seconds=2, milliseconds=456),
            duration_union=None,
        )
    )

    # We should only have one more error log
    error_logs = [
        entry
        for entry in log_output.entries
        if entry.get("attempted_operation") == "publish"
    ]
    assert len(error_logs) == 2


@pytest.mark.asyncio
async def test_bad_kafka_from_start_raises() -> None:
    bad_kafka_settings = KafkaConnectionSettings(
        bootstrap_servers="nope:1234,nada:5678",
        security_protocol=SecurityProtocol.PLAINTEXT,
    )

    bad_schema_manager_settings = SchemaManagerSettings(
        registry_url=HttpUrl("https://nope.com")
    )
    config = KafkaMetricsConfiguration(
        application="testapp",
        enabled=True,
        events=EventsConfiguration(topic_prefix="what.ever"),
        kafka=bad_kafka_settings,
        schema_manager=bad_schema_manager_settings,
        raise_on_error=True,
    )

    manager = config.make_manager()

    with pytest.raises(KafkaConnectionError):
        await manager.initialize()


# This test intetionally breaks aiokafka clients in an unclean way. When the
# aiokafka objects get garbage collected, Python asyncio logs warning messages
# that task exceptions were never retrieved. The time that this happens is not
# deterministic. It can mess up other tests, like tests of the Sentry
# functionality because the log messages get picked up by the mock Sentry
# transport if they happen after the Sentry fixtures have initialized. There
# may be a way to deterministically and cleanly cancel these failed tasks, or
# it may be a but in the aiokafka library, but until we figure it out we run
# these last to make sure they don't infect other tests.
@pytest.mark.order(-1)
@pytest.mark.asyncio
async def test_bad_kafka_after_initialize(
    resiliency_metrics_stack: MetricsStack,
    log_output: LogCapture,
    time_machine: TimeMachineFixture,
) -> None:
    event_manager = resiliency_metrics_stack.event_manager
    await event_manager.initialize()
    kafka_container = resiliency_metrics_stack.kafka_stack.kafka_container
    schema_registry_client = (
        resiliency_metrics_stack.kafka_clients.schema_registry_client
    )
    max_batch_size = resiliency_metrics_stack.kafka_max_batch_size
    backoff_interval = resiliency_metrics_stack.metrics_config.backoff_interval
    kafka_connection_settings = (
        resiliency_metrics_stack.kafka_stack.kafka_connection_settings
    )

    # We're gonna call a method on this, so tell the type checker it's not None
    assert event_manager._broker._producer

    # Create an events dependency
    events_dependency = EventDependency(Events())
    await events_dependency.initialize(manager=event_manager)

    event = events_dependency.events.my_event

    # This should make it to kafka
    await event.publish(
        MyEvent(
            foo="working",
            duration=timedelta(seconds=2, milliseconds=123),
            duration_union=None,
        )
    )
    await flush_producer(event_manager)

    # Stop Kafka
    kafka_container.stop_container()

    # Quickly sending a bunch more messages than max_batch_size is set to
    # should get us an exception here. None of these should make it to Kafka.
    #
    # Sometimes, exceptions from aiokafka will be raised here, and sometimes
    # they will be raised in futures. If we send so many messages so quickly
    # that the message batch gets filled up, then send calls will block until
    # the batch is sent, and we'll get an exception here if the batch can't be
    # sent. If a batch never gets filled up before getting sent, then the
    # exception will be sitting in a future.
    for _ in range(max_batch_size + 5):
        await event.publish(
            MyEvent(
                foo="stopped",
                duration=timedelta(seconds=2, milliseconds=456),
                duration_union=None,
            )
        )
    await flush_producer(event_manager)

    # This shouldn't raise an exception, but it shouldn't make it to kafka.
    await event.publish(
        MyEvent(
            foo="stopped",
            duration=timedelta(seconds=2, milliseconds=456),
            duration_union=None,
        )
    )
    await flush_producer(event_manager)

    # There should be one error event in the logs
    error_logs = [
        entry
        for entry in log_output.entries
        if entry["log_level"] == "error"
        and entry["attempted_operation"] == "publish"
    ]
    assert len(error_logs) == 1

    # Move time to after the backoff window. This isn't EXACTLY when the
    # backoff interval expires, but it's close enough for testing.
    time_machine.move_to(datetime.now(tz=UTC) + backoff_interval, tick=True)

    # These should also not make it to Kafka, but there should be one more
    # error log because we're past the backoff window
    for _ in range(max_batch_size + 5):
        await event.publish(
            MyEvent(
                foo="in_backoff",
                duration=timedelta(seconds=2, milliseconds=456),
                duration_union=None,
            )
        )
    await flush_producer(event_manager)

    backoff_down_error_logs = [
        entry
        for entry in log_output.entries
        if entry["log_level"] == "error"
        and entry["attempted_operation"] == "publish"
    ]
    assert len(backoff_down_error_logs) == len(error_logs) + 1

    # Start kafka again
    kafka_container.start_container_again()

    # These should also not make it to Kafka, even though it's back up, because
    # we're still in the backoff window
    for _ in range(max_batch_size + 5):
        await event.publish(
            MyEvent(
                foo="in_backoff_again",
                duration=timedelta(seconds=2, milliseconds=456),
                duration_union=None,
            )
        )

    # We still should not have any more error logs because we're still in the
    # backoff window
    backoff_up_error_logs = [
        entry
        for entry in log_output.entries
        if entry["log_level"] == "error"
        and entry["attempted_operation"] == "publish"
    ]
    await flush_producer(event_manager)
    assert len(backoff_up_error_logs) == len(backoff_down_error_logs)

    # Move time to after the next backoff window. This isn't EXACTLY when the
    # backoff interval expires, but it's close enough for testing.
    time_machine.move_to(datetime.now(tz=UTC) + backoff_interval, tick=True)

    # These should all make it to Kafka
    for _ in range(max_batch_size + 5):
        await event.publish(
            MyEvent(
                foo="started_again",
                duration=timedelta(seconds=2, milliseconds=456),
                duration_union=None,
            )
        )
    await flush_producer(event_manager)

    # There shouldn't be any more error logs
    new_error_logs = [
        entry for entry in log_output.entries if entry["log_level"] == "error"
    ]
    assert len(new_error_logs) == len(backoff_up_error_logs)

    consumer = AIOKafkaConsumer(
        **kafka_connection_settings.to_aiokafka_params(),
        client_id="pytest-consumer",
    )

    # Verify messages made it to Kafka
    try:
        await consumer.start()
        await subscribe_and_wait(consumer, "what.ever.testapp")
        await consumer.seek_to_beginning()
        topic = TopicPartition(topic="what.ever.testapp", partition=0)
        message_groups = await consumer.getmany(
            topic,
            timeout_ms=10000,
        )
    finally:
        await consumer.stop()

    messages = message_groups[topic]
    serializer = AsyncAvroMessageSerializer(schema_registry_client)
    deserialized = [
        await serializer.decode_message(message.value) for message in messages
    ]

    working = [m for m in deserialized if m and m.get("foo") == "working"]
    started_again = [
        m for m in deserialized if m and m.get("foo") == "started_again"
    ]

    # Kafka should have the only the messages from before we stopped the
    # container, and the messages from after we restarted the container and
    # after the backoff interval.
    assert len(deserialized) == max_batch_size + 5 + 1

    assert len(working) == 1
    assert len(started_again) == max_batch_size + 5


# This test intetionally breaks aiokafka clients in an unclean way. When the
# aiokafka objects get garbage collected, Python asyncio logs warning messages
# that task exceptions were never retrieved. The time that this happens is not
# deterministic. It can mess up other tests, like tests of the Sentry
# functionality because the log messages get picked up by the mock Sentry
# transport if they happen after the Sentry fixtures have initialized. There
# may be a way to deterministically and cleanly cancel these failed tasks, or
# it may be a but in the aiokafka library, but until we figure it out we run
# these last to make sure they don't infect other tests.
@pytest.mark.order(-1)
@pytest.mark.asyncio
async def test_bad_schema_manager_mid_registration(
    resiliency_metrics_stack: MetricsStack,
    log_output: LogCapture,
    time_machine: TimeMachineFixture,
) -> None:
    event_manager = resiliency_metrics_stack.event_manager
    registry = resiliency_metrics_stack.kafka_stack.schema_registry_container
    backoff_interval = resiliency_metrics_stack.metrics_config.backoff_interval

    # This should be a legit event publisher
    event = await event_manager.create_publisher("myevent", MyEvent)

    registry.stop()

    # This should be a failed event publisher
    other_event = await event_manager.create_publisher(
        "myotherevent", MyOtherEvent
    )

    # These shouldn't raise exceptions, and they shouldn't make it to kafka.
    await event.publish(
        MyEvent(
            foo="stopped",
            duration=timedelta(seconds=2, milliseconds=456),
            duration_union=None,
        )
    )
    await other_event.publish(
        MyOtherEvent(
            bar="stopped",
            duration=timedelta(seconds=2, milliseconds=456),
            duration_union=None,
        )
    )

    # There should be one error from trying to build the publisher, and one
    # error from trying to publish with the FailedPublisher
    (build_error, publish_error) = log_output.entries
    assert build_error["attempted_operation"] == "_build_publisher_for_model"
    assert publish_error["attempted_operation"] == "publish"

    # Clear the log output
    log_output.entries = []

    # Move time to after the next backoff window. This isn't EXACTLY when the
    # backoff interval expires, but it's close enough for testing.
    time_machine.move_to(datetime.now(tz=UTC) + backoff_interval, tick=True)

    await event.publish(
        MyEvent(
            foo="stopped",
            duration=timedelta(seconds=2, milliseconds=456),
            duration_union=None,
        )
    )
    await other_event.publish(
        MyOtherEvent(
            bar="stopped",
            duration=timedelta(seconds=2, milliseconds=456),
            duration_union=None,
        )
    )

    assert len(log_output.entries) == 2
    operations = [entry["attempted_operation"] for entry in log_output.entries]
    assert all(op == "publish" for op in operations)
