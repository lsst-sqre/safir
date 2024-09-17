from collections.abc import Callable
from typing import Generic, TypeVar

from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka import KafkaBroker

from ..kafka.config import KafkaConnectionSettings
from ..schema_manager.config import SchemaManagerSettings
from ..schema_manager.pydantic_schema_manager import PydanticSchemaManager
from .event_manager import EventManager

E = TypeVar("E")


class EventsDependency(Generic[E]):
    """Provides events for the app to publish."""

    def __init__(self, event_maker: Callable[[EventManager], E]) -> None:
        self._events: E | None = None
        self._event_maker = event_maker
        self._manager: EventManager

    async def initialize(
        self,
        *,
        manager: EventManager,
        kafka_broker: KafkaBroker | KafkaConnectionSettings | None,
        kafka_admin_client: AIOKafkaAdminClient
        | KafkaConnectionSettings
        | None,
        schema_manager: PydanticSchemaManager | SchemaManagerSettings | None,
    ) -> None:
        self._events = self._event_maker(manager)
        self._manager = manager
        await manager.register_events(
            kafka_broker=kafka_broker,
            kafka_admin_client=kafka_admin_client,
            schema_manager=schema_manager,
        )

    @property
    def events(self) -> E:
        if not self._events:
            raise RuntimeError("EventsDependency not initialized")
        return self._events

    def __call__(self) -> E:
        return self.events

    async def aclose(self) -> None:
        await self._manager.aclose()
