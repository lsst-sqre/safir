"""Test metrics development tools."""

import asyncio
import math
from uuid import UUID

import pytest
from aiokafka import AIOKafkaConsumer
from pydantic import AnyUrl

from safir.kafka.config import KafkaConnectionSettings, KafkaSecurityProtocol
from safir.metrics.config import MetricsConfiguration
from safir.metrics.event_manager import (
    Event,
    EventManager,
    create_event_manager_from_config,
)
from safir.metrics.models import EventMetadata, Payload
from safir.schema_manager.config import (
    SchemaManagerSettings,
    SchemaRegistryConnectionSettings,
)


async def subscribe_and_wait(consumer: AIOKafkaConsumer, pattern: str) -> None:
    # There is some race condition in where an exception is raised if we start
    # trying to consume messages too soon after we have subscribed to a topic
    # or pattern, because partitions haven't been assigned to the consumer yet.
    consumer.subscribe(pattern=pattern)
    await asyncio.sleep(0.5)


class MyEvent(Payload):
    foo: str


async def assert_event_from_kafka(
    consumer: AIOKafkaConsumer,
    manager: EventManager,
    event: Event[MyEvent],
    foo: str,
) -> None:
    """Deserialize a published event back into its model type."""
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


@pytest.mark.asyncio
async def test_integration(
    kafka_bootstrap_server: str,
    schema_registry_url: str,
    kafka_consumer: AIOKafkaConsumer,
) -> None:
    kafka_settings = KafkaConnectionSettings(
        bootstrap_servers=kafka_bootstrap_server,
        security_protocol=KafkaSecurityProtocol.PLAINTEXT,
    )
    schema_manager_settings = SchemaManagerSettings(
        schema_registry=SchemaRegistryConnectionSettings(
            url=AnyUrl(schema_registry_url)
        )
    )

    config = MetricsConfiguration(
        service="test-app",
        base_topic_prefix="what.ever",
    )
    manager = create_event_manager_from_config(config)
    event = manager.create_event(MyEvent)
    await manager.register_events(
        kafka_broker=kafka_settings,
        kafka_admin_client=kafka_settings,
        schema_manager=schema_manager_settings,
    )
    await event.publish(MyEvent(foo="bar1"))
    await event.publish(MyEvent(foo="bar2"))
    await manager.aclose()

    topic = "what.ever.test-app.MyEvent"
    assert event.topic == topic

    await subscribe_and_wait(consumer=kafka_consumer, pattern=topic)
    await kafka_consumer.seek_to_beginning()

    await assert_event_from_kafka(kafka_consumer, manager, event, "bar1")
    await assert_event_from_kafka(kafka_consumer, manager, event, "bar2")


@pytest.mark.asyncio
async def test_noop() -> None:
    config = MetricsConfiguration(
        service="test-app",
        base_topic_prefix="what.ever",
        noop=True,
    )
    manager = create_event_manager_from_config(config)

    event = manager.create_event(MyEvent)
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
