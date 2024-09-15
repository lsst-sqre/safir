"""Test metrics development tools."""

import asyncio
import math
from uuid import UUID

import pytest
from aiokafka import AIOKafkaConsumer
from pydantic import AnyUrl

from safir.kafka.config import KafkaConnectionSettings, KafkaSecurityProtocol
from safir.metrics.event_manager import Event, EventManager, NoopEventManager
from safir.metrics.models import EventMetadata, Payload
from safir.schema_manager.config import (
    SchemaManagerSettings,
    SchemaRegistryConnectionSettings,
)


class MyEvent(Payload):
    foo: str


async def publish(manager: EventManager) -> Event[MyEvent]:
    """Works with a real or no-op event manager."""
    event = manager.create_event("my_event", MyEvent)

    await manager.initialize_events()
    await event.publish(MyEvent(foo="bar1"))
    await event.publish(MyEvent(foo="bar2"))
    await manager.aclose()
    return event


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
        message.value, event._event_class
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

    manager = EventManager()
    await manager.initialize(
        service="test-app",
        base_topic_prefix="what.ever",
        kafka_broker=kafka_settings,
        kafka_admin_client=kafka_settings,
        schema_manager=schema_manager_settings,
    )
    event = await publish(manager)
    topic = "what.ever.test-app.my_event"
    assert event._topic == topic

    kafka_consumer.subscribe(pattern=topic)
    await asyncio.sleep(1)
    await kafka_consumer.seek_to_beginning()

    await assert_event_from_kafka(kafka_consumer, manager, event, "bar1")
    await assert_event_from_kafka(kafka_consumer, manager, event, "bar2")


@pytest.mark.asyncio
async def test_noop() -> None:
    manager = NoopEventManager()

    await publish(manager)
