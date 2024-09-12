"""Test metrics development tools."""

import time
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest
from freezegun import freeze_time

from safir.metrics.event_manager import EventManager
from safir.metrics.models import Payload


@pytest.mark.asyncio
async def test_integration(
    kafka_bootstrap_server: str, schema_registry_url: str
) -> None:
    print("blah")
    breakpoint()
    print("nope")


@freeze_time("2022-03-13")
@pytest.mark.asyncio
async def test_mock_mode() -> None:
    expected_timestamp_ns = time.time_ns()
    expected_timestamp = datetime.now(tz=UTC)
    manager = EventManager()

    await manager.initialize(
        service="test-app",
        base_topic_prefix="what.ever",
        kafka_broker=Mock(),
        kafka_admin_client=Mock(),
        schema_manager=Mock(),
        mock_mode=True,
    )

    class MyEvent(Payload):
        foo: str

    event = manager.create_event("my_event", MyEvent)
    assert event._topic == "what.ever.test-app.my_event"

    await manager.initialize_events()
    await event.publish(MyEvent(foo="bar"))
    await event.publish(MyEvent(foo="bar2"))
    await manager.aclose()

    published = event.published_events[0]
    assert isinstance(published.id, UUID)  # type: ignore[attr-defined]
    assert published.service == "test-app"  # type: ignore[attr-defined]
    assert published.timestamp_ns == expected_timestamp_ns  # type: ignore[attr-defined]
    assert published.timestamp == expected_timestamp  # type: ignore[attr-defined]
    assert published.foo == "bar"  # type: ignore[attr-defined]
    await manager.initialize_events()
    await manager.aclose()

    published = event.published_events[1]
    assert isinstance(published.id, UUID)  # type: ignore[attr-defined]
    assert published.service == "test-app"  # type: ignore[attr-defined]
    assert published.timestamp_ns == expected_timestamp_ns  # type: ignore[attr-defined]
    assert published.timestamp == expected_timestamp  # type: ignore[attr-defined]
    assert published.foo == "bar2"  # type: ignore[attr-defined]
    await manager.initialize_events()
    await manager.aclose()

    assert [
        MyEvent(foo="bar"),
        MyEvent(foo="bar2"),
    ] == event.published_payloads
