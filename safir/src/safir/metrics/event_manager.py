"""Tools for publishing events for later analysis."""

from __future__ import annotations

import ssl
import time
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import uuid4

from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from dataclasses_avroschema.pydantic import AvroBaseModel
from faststream.kafka import KafkaBroker
from faststream.security import SASLScram512
from pydantic import create_model
from schema_registry.client import AsyncSchemaRegistryClient
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)

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
        serializer: AsyncAvroMessageSerializer,
        registry_client: AsyncSchemaRegistryClient,
        payload_model: type[P],
    ) -> None:
        self._name = name
        self._service = service
        self.topic = topic
        self._broker = broker
        self._serializer = serializer
        self._registry_client = registry_client
        self._schema_id: int | None = None

        class MetaBase(AvroBaseModel):
            class Meta:
                schema_name = topic

        self._event_class = create_model(
            "EventModel",
            __base__=(payload_model, EventMetadata, MetaBase),
        )

        if not issubclass(self._event_class, AvroBaseModel):
            raise TypeError(
                "This can never happen, but mypy can't figure that out."
            )

        self._avro_schema = self._event_class.avro_schema()
        self._publisher = self._broker.publisher(
            topic, schema=self._event_class
        )

    async def register_schema(self) -> int:
        self._schema_id = await self._registry_client.register(
            self.topic, self._avro_schema
        )
        return self._schema_id

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

        if self._schema_id is None:
            self._schema_id = await self.register_schema()

        encoded = await self._serializer.encode_record_with_schema_id(
            self._schema_id, event.model_dump()
        )
        await self._publisher.publish(encoded)

    def _ns_to_datetime(self, ns: int) -> datetime:
        return datetime.fromtimestamp(ns / 1e9, tz=UTC)


class EventManager:
    """Yep."""

    def __init__(self) -> None:
        self._service: str
        self._broker: KafkaBroker
        self._admin_client: AIOKafkaAdminClient
        self._registry_client: AsyncSchemaRegistryClient
        self._serializer: AsyncAvroMessageSerializer
        self._topic_prefix: str
        self._events: dict[str, Event] = {}

    async def initialize(
        self,
        service: str,
        base_topic_prefix: str,
        bootstrap_servers: str,
        sasl_username: str,
        sasl_password: str,
        schema_registry_url: str,
    ) -> None:
        self._service = service
        self._topic_prefix = f"{base_topic_prefix}.{service}"

        ssl_context = ssl.create_default_context()
        self._broker = KafkaBroker(
            bootstrap_servers=bootstrap_servers,
            client_id=f"safir-metrics-client-{self._service}",
            security=SASLScram512(
                username=sasl_username,
                password=sasl_password,
                ssl_context=ssl_context,
            ),
        )
        self._admin_client = AIOKafkaAdminClient(
            bootstrap_servers=[
                "sasquatch-dev-kafka-bootstrap.lsst.cloud:9094"
            ],
            client_id="dfuchs-test-metrics-admin",
            security_protocol="SASL_SSL",
            sasl_mechanism="SCRAM-SHA-512",
            sasl_plain_username=sasl_username,
            sasl_plain_password=sasl_password,
            ssl_context=ssl_context,
        )

        self._registry_client = AsyncSchemaRegistryClient(
            url=schema_registry_url
        )

        self._serializer = AsyncAvroMessageSerializer(self._registry_client)

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
            serializer=self._serializer,
            registry_client=self._registry_client,
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
