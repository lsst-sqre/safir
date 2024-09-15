import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import uuid4

from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from dataclasses_avroschema.pydantic import AvroBaseModel
from faststream.kafka import KafkaBroker
from faststream.kafka.publisher.asyncapi import AsyncAPIDefaultPublisher
from pydantic import create_model
from structlog.stdlib import BoundLogger

from ..schema_manager.pydantic_schema_manager import (
    PydanticSchemaManager,
    SchemaInfo,
)
from .models import EventMetadata, Payload

P = TypeVar("P", bound=Payload)


class BaseEvent(Generic[P], ABC):
    @abstractmethod
    async def publish(self, payload: P) -> None: ...


class NoopEvent(BaseEvent, Generic[P]):
    def __init__(
        self,
        *,
        name: str,
        namespace: str,
        service: str,
        topic: str,
        payload_model: type[P],
        logger: BoundLogger,
    ) -> None:
        self._name = name
        self._namespace = namespace
        self._service = service
        self._topic = topic
        self._logger = logger

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

    async def publish(self, payload: P) -> None:
        self._logger.debug(
            "Would have published metrics payload",
            metrics_event=payload.model_dump(),
        )


class Event(NoopEvent, Generic[P]):
    def __init__(
        self,
        *,
        name: str,
        namespace: str,
        service: str,
        topic: str,
        payload_model: type[P],
        logger: BoundLogger,
    ) -> None:
        super().__init__(
            name=name,
            namespace=namespace,
            service=service,
            topic=topic,
            payload_model=payload_model,
            logger=logger,
        )
        self._schema_info: SchemaInfo
        self._broker: KafkaBroker
        self._admin_client: AIOKafkaAdminClient
        self._schema_manager: PydanticSchemaManager
        self._publisher: AsyncAPIDefaultPublisher

    async def initialize(
        self,
        broker: KafkaBroker,
        admin_client: AIOKafkaAdminClient,
        schema_manager: PydanticSchemaManager,
    ) -> None:
        self._broker = broker
        self._admin_client = admin_client
        self._schema_manager = schema_manager
        self._publisher = self._broker.publisher(
            self._topic, schema=self._event_class
        )

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

        self._logger.debug(
            "Published metrics event",
            metrics_event=event.model_dump(),
            topic=self._topic,
            schema_info=self._schema_info,
        )

    def _ns_to_datetime(self, ns: int) -> datetime:
        return datetime.fromtimestamp(ns / 1e9, tz=UTC)
