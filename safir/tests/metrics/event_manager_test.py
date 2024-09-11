"""Test metrics development tools."""

import pytest
from freezegun import freeze_time

from safir.metrics.development import make_noop_storage
from safir.metrics.event_manager import EventManager
from safir.metrics.models import Payload


@freeze_time("2022-03-13")
@pytest.mark.asyncio
async def test_noop() -> None:
    manager = EventManager()
    await manager.initialize(
        service="test-app",
        base_topic_prefix="what.ever",
        storage=make_noop_storage(),
    )

    class MyEvent(Payload):
        foo: str

    event = manager.create_event("my_event", MyEvent)
    await manager.initialize_events()

    await event.publish(MyEvent(foo="bar"))
    breakpoint()
