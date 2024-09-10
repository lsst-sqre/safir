"""Tools for publishing events for later analysis."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import uuid4

from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from dataclasses_avroschema.pydantic import AvroBaseModel
from faststream.kafka import KafkaBroker
from pydantic import create_model
from schema_registry.client import AsyncSchemaRegistryClient
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)

from safir.kafka.aiokafka_admin_client import make_kafka_admin_client
from safir.kafka.config import KafkaConnectionSettings
from safir.kafka.faststream_kafka_broker import make_kafka_broker
from safir.schema_registry.client import make_schema_registry_client
from safir.schema_registry.config import SchemaRegistryConnectionSettings

from ..schema_registry.pydantic_schema_manager import PydanticSchemaManager
from .models import EventMetadata, Payload

P = TypeVar("P", bound=Payload)


class Event(Generic[P]):
    """A publisher for one specific type of event."""

    def __init__(
        self,
        name: str,
        service: str,
        topic: str,
        broker: KafkaBroker,
        schema_manager: PydanticSchemaManager,
        payload_model: type[P],
    ) -> None:
        self._name = name
        self._service = service
        self.topic = topic
        self._broker = broker
        self._schema_manager = schema_manager
        self._schema_id: int | None = None

        class MetaBase(AvroBaseModel):
            class Meta:
                schema_name = topic

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

    async def register_schema(self) -> None:
        await self._schema_manager.register_model(self._event_class)

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

    def _ns_to_datetime(self, ns: int) -> datetime:
        return datetime.fromtimestamp(ns / 1e9, tz=UTC)


class EventManager:
    """Yep."""

    def __init__(self, schema_suffix: str = "") -> None:
        self._schema_suffix = schema_suffix
        self._service: str
        self._broker: KafkaBroker
        self._admin_client: AIOKafkaAdminClient
        self._registry: AsyncSchemaRegistryClient
        self._serializer: AsyncAvroMessageSerializer
        self._topic_prefix: str
        self._schema_manager: PydanticSchemaManager
        self._events: dict[str, Event] = {}

    async def initialize(
        self,
        service: str,
        base_topic_prefix: str,
        kafka_config: KafkaConnectionSettings,
        schema_registry_config: SchemaRegistryConnectionSettings,
    ) -> None:
        self._service = service
        self._topic_prefix = f"{base_topic_prefix}.{service}"

        self._broker = make_kafka_broker(
            kafka_config, client_id=f"safir-metrics-client-{self._service}"
        )
        self._admin_client = make_kafka_admin_client(
            kafka_config,
            client_id=f"safir-metrics-admin-client-{self._service}",
        )

        self._registry = make_schema_registry_client(schema_registry_config)

        self._schema_manager = PydanticSchemaManager(
            registry=self._registry, suffix=self._schema_suffix
        )

        await self._broker.start()
        await self._admin_client.start()

    def create_event(self, name: str, payload_model: type[P]) -> Event[P]:
        if name in self._events:
            raise RuntimeError(
                f"{name}: you have already created an event with this name."
                " Events must have unique names within this application."
            )
        event = Event(
            name=name,
            service=self._service,
            topic=f"{self._topic_prefix}.{name}",
            broker=self._broker,
            schema_manager=self._schema_manager,
            payload_model=payload_model,
        )
        self._events[name] = event
        return event

    async def create_topics(self) -> None:
        for event in self._events.values():
            topic = NewTopic(
                name=event.topic,
                num_partitions=1,
                replication_factor=3,
            )
            await self._admin_client.create_topics([topic])

    async def register_schemas(self) -> None:
        for event in self._events.values():
            await event.register_schema()

    async def aclose(self) -> None:
        await self._broker.close()
        await self._admin_client.close()
