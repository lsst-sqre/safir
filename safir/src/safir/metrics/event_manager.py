"""Tools for publishing events for later analysis."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, TypeVar
from unittest.mock import AsyncMock
from uuid import uuid4

import structlog
from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from dataclasses_avroschema.pydantic import AvroBaseModel
from faststream.kafka import KafkaBroker
from pydantic import create_model
from structlog.stdlib import BoundLogger

from ..kafka.aiokafka_admin_client import make_kafka_admin_client
from ..kafka.config import KafkaConnectionSettings
from ..kafka.faststream_kafka_broker import make_kafka_broker
from ..schema_manager.config import SchemaManagerSettings
from ..schema_manager.pydantic_schema_manager import (
    PydanticSchemaManager,
    SchemaInfo,
)
from .models import EventMetadata, Payload

P = TypeVar("P", bound=Payload)


class Event(Generic[P]):
    """A publisher for one specific type of event."""

    def __init__(
        self,
        *,
        name: str,
        namespace: str,
        service: str,
        topic: str,
        broker: KafkaBroker,
        admin_client: AIOKafkaAdminClient,
        schema_manager: PydanticSchemaManager,
        payload_model: type[P],
        logger: BoundLogger,
        mock_mode: bool = False,
    ) -> None:
        self._name = name
        self._namespace = namespace
        self._service = service
        self._topic = topic
        self._broker = broker
        self._admin_client = admin_client
        self._schema_manager = schema_manager
        self._schema_info: SchemaInfo
        self._logger = logger
        self._published_payloads: list[P] | None = None
        self._published_events: list[AvroBaseModel] | None = None

        if mock_mode:
            self._published_payloads = []
            self._published_events = []

        class MetaBase(AvroBaseModel):
            class Meta:
                schema_name = self._name
                namespace = self._namespace

        event_class = create_model(
            "EventModel",
            __base__=(payload_model, EventMetadata, MetaBase),
        )

        if not issubclass(event_class, AvroBaseModel):
            raise TypeError(
                "This can never happen, but mypy can't figure that out."
            )
        self._event_class: type[AvroBaseModel] = event_class

        self._publisher = self._broker.publisher(
            topic, schema=self._event_class
        )

    async def initialize(self) -> None:
        """Ensure a kafka topic exists and the event schema is registered."""
        topic = NewTopic(
            name=self._topic,
            num_partitions=1,
            replication_factor=3,
        )
        await self._admin_client.create_topics([topic])

        self._schema_info = await self._schema_manager.register_model(
            self._event_class
        )

    async def publish(self, payload: P) -> None:
        """Publish an event."""
        time_ns = time.time_ns()
        metadata = EventMetadata(
            id=uuid4(),
            service=self._service,
            timestamp=self._ns_to_datetime(time_ns),
            timestamp_ns=time_ns,
        )
        event = self._event_class(
            **metadata.model_dump(), **payload.model_dump()
        )

        encoded = await self._schema_manager.serialize(event)
        await self._publisher.publish(encoded)

        if self._published_payloads is not None:
            self._published_payloads.append(payload)
        if self._published_events is not None:
            self._published_events.append(event)

        self._logger.debug(
            "Published metrics event",
            metrics_event=event.model_dump(),
            topic=self._topic,
            schema_info=self._schema_info,
        )

    @property
    def published_payloads(self) -> list[P]:
        if self._published_payloads is None:
            raise RuntimeError(
                "Event manager must be running in mock mode to remember"
                " published payloads."
            )
        return self._published_payloads

    @property
    def published_events(self) -> list[AvroBaseModel]:
        if self._published_events is None:
            raise RuntimeError(
                "Event manager must be running in mock mode to remember"
                " published events."
            )
        return self._published_events

    def _ns_to_datetime(self, ns: int) -> datetime:
        return datetime.fromtimestamp(ns / 1e9, tz=UTC)


@dataclass
class _EventManagerStorage:
    kafka_broker: KafkaBroker | KafkaConnectionSettings
    kafka_admin_client: AIOKafkaAdminClient | KafkaConnectionSettings
    schema_manager: PydanticSchemaManager | SchemaManagerSettings


class EventManager:
    """Yep."""

    def __init__(self) -> None:
        self._service: str
        self._topic_prefix: str
        self._logger: BoundLogger

        # Dependencies
        self._broker: KafkaBroker
        self._manage_broker: bool
        self._admin_client: AIOKafkaAdminClient
        self._manage_admin_client: bool
        self._schema_manager: PydanticSchemaManager
        self._mock_mode = False

        self._events: dict[str, Event] = {}

    async def initialize(
        self,
        *,
        service: str,
        base_topic_prefix: str,
        kafka_broker: KafkaBroker | KafkaConnectionSettings,
        kafka_admin_client: AIOKafkaAdminClient | KafkaConnectionSettings,
        schema_manager: PydanticSchemaManager | SchemaManagerSettings,
        logger: BoundLogger | None = None,
        mock_mode: bool = False,
    ) -> None:
        self._service = service
        self._topic_prefix = f"{base_topic_prefix}.{service}"
        self._logger = logger or structlog.get_logger("metrics_event_manager")
        self._mock_mode = mock_mode

        if self._mock_mode:
            self._logger.warning(
                "No metrics events will be sent, because the EventManager is"
                " running in mock mode. ``kafka_broker``,"
                " ``kafka_admin_client``, and ``schema_manager`` will all be"
                " mocked. Values provided for those parameters will be"
                " ignored."
            )
            storage = self._make_mock_event_manager_storage()
            kafka_broker = storage.kafka_broker
            kafka_admin_client = storage.kafka_admin_client
            schema_manager = storage.schema_manager

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

    def _make_mock_event_manager_storage(self) -> _EventManagerStorage:
        """Construct a collection of no-op storage objects."""
        mock_kafka_broker = AsyncMock(KafkaBroker)
        mock_kafka_broker.publisher.return_value = AsyncMock()

        return _EventManagerStorage(
            kafka_broker=mock_kafka_broker,
            kafka_admin_client=AsyncMock(AIOKafkaAdminClient),
            schema_manager=AsyncMock(PydanticSchemaManager),
        )

    def create_event(self, name: str, payload_model: type[P]) -> Event[P]:
        if name in self._events:
            raise RuntimeError(
                f"{name}: you have already created an event with this name."
                " Events must have unique names within this application."
            )
        event = Event(
            name=name,
            namespace=self._topic_prefix,
            service=self._service,
            topic=f"{self._topic_prefix}.{name}",
            broker=self._broker,
            schema_manager=self._schema_manager,
            admin_client=self._admin_client,
            payload_model=payload_model,
            logger=self._logger,
            mock_mode=self._mock_mode,
        )
        self._events[name] = event
        return event

    async def initialize_events(self) -> None:
        for event in self._events.values():
            await event.initialize()

    async def aclose(self) -> None:
        if self._manage_broker:
            await self._broker.close()
        if self._manage_admin_client:
            await self._admin_client.close()
