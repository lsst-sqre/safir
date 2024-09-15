"""Tools for publishing events for later analysis."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

import structlog
from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka import KafkaBroker
from structlog.stdlib import BoundLogger

from ..kafka.aiokafka_admin_client import make_kafka_admin_client
from ..kafka.config import KafkaConnectionSettings
from ..kafka.faststream_kafka_broker import make_kafka_broker
from ..schema_manager.config import SchemaManagerSettings
from ..schema_manager.pydantic_schema_manager import PydanticSchemaManager
from .event import BaseEvent, Event, NoopEvent
from .models import Payload

P = TypeVar("P", bound=Payload)
E = TypeVar("E", bound=BaseEvent)


class BaseEventManager(ABC, Generic[E]):
    @abstractmethod
    def create_event(self, name: str, payload_model: type[P]) -> E: ...

    @abstractmethod
    async def initialize_events(self) -> None: ...

    @abstractmethod
    async def aclose(self) -> None: ...


class NoopEventManager(BaseEventManager[NoopEvent]):
    def __init__(
        self,
        service: str,
        base_topic_prefix: str,
        logger: BoundLogger | None = None,
    ) -> None:
        self._service = service
        self._topic_prefix = f"{base_topic_prefix}.{service}"
        self._logger = logger or structlog.get_logger("metrics_event_manager")
        self._events: dict[str, NoopEvent] = {}
        self._event_type: E = NoopEvent

    def create_event(self, name: str, payload_model: type[P]) -> BaseEvent[P]:
        if name in self._events:
            raise RuntimeError(
                f"{name}: you have already created an event with this name."
                " Events must have unique names within this application."
            )
        return self._event_type(
            name=name,
            namespace=self._topic_prefix,
            service=self._service,
            topic=f"{self._topic_prefix}.{name}",
            payload_model=payload_model,
            logger=self._logger,
        )

    async def initialize_events(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


class EventManager(NoopEventManager):
    def __init__(
        self,
        service: str,
        base_topic_prefix: str,
        logger: BoundLogger | None = None,
    ) -> None:
        super().__init__(
            service=service, base_topic_prefix=base_topic_prefix, logger=logger
        )
        self._broker: KafkaBroker
        self._manage_broker: bool
        self._admin_client: AIOKafkaAdminClient
        self._manage_admin_client: bool
        self._schema_manager: PydanticSchemaManager
        self._event_class = type[Event]

        self._events: dict[str, Event] = {}

    def create_event(self, name: str, payload_model: type[P]) -> Event[P]:
        event = super().create_event(name=name, payload_model=payload_model)
        self._events[name] = event
        return event

    async def initialize(
        self,
        *,
        kafka_broker: KafkaBroker | KafkaConnectionSettings,
        kafka_admin_client: AIOKafkaAdminClient | KafkaConnectionSettings,
        schema_manager: PydanticSchemaManager | SchemaManagerSettings,
    ) -> None:
        match kafka_broker:
            case KafkaBroker():
                self._broker = kafka_broker
                self._manage_broker = False
            case KafkaConnectionSettings():
                self._broker = make_kafka_broker(
                    kafka_broker,
                    client_id=f"safir-metrics-client-{self._service}",
                )
                await self._broker.start()
                self._manage_broker = True

        match kafka_admin_client:
            case AIOKafkaAdminClient():
                self._admin_client = kafka_admin_client
                self._manage_admin_client = False
            case KafkaConnectionSettings():
                self._admin_client = make_kafka_admin_client(
                    kafka_admin_client,
                    client_id=f"safir-metrics-admin-client-{self._service}",
                )
                await self._admin_client.start()
                self._manage_admin_client = True

        match schema_manager:
            case PydanticSchemaManager():
                self._schema_manager = schema_manager
            case SchemaManagerSettings():
                self._schema_manager = PydanticSchemaManager.from_config(
                    schema_manager
                )

    async def initialize_events(self) -> None:
        for event in self._events.values():
            await event.initialize(
                broker=self._broker,
                schema_manager=self._schema_manager,
                admin_client=self._admin_client,
            )

    async def aclose(self) -> None:
        if self._manage_broker:
            await self._broker.close()
        if self._manage_admin_client:
            await self._admin_client.close()
