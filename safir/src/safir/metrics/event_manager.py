"""Tools for publishing events for later analysis."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import uuid4

import structlog
from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from dataclasses_avroschema.pydantic import AvroBaseModel
from faststream.kafka import KafkaBroker
from faststream.kafka.publisher.asyncapi import AsyncAPIDefaultPublisher
from pydantic import create_model
from structlog.stdlib import BoundLogger

from safir.metrics.config import MetricsConfiguration

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


class Publisher(Generic[P]):
    def __init__(
        self,
        *,
        name: str,
        topic: str,
        namespace: str,
        payload_model: type[P],
        manager: EventManager,
    ) -> None:
        self.name = name
        self.topic = topic
        self.namespace = namespace
        self.schema_info: SchemaInfo
        self.publisher: AsyncAPIDefaultPublisher
        self.manager = manager

        class MetaBase(AvroBaseModel):
            class Meta:
                schema_name = self.name
                namespace = self.namespace

        event_class = create_model(
            "EventModel",
            __base__=(payload_model, EventMetadata, MetaBase),
        )

        if not issubclass(event_class, AvroBaseModel):
            raise TypeError(
                "This can never happen, but mypy can't figure that out."
            )
        self.event_class: type[AvroBaseModel] = event_class

    async def publish(self, payload: P) -> None:
        await self.manager.publish(self, payload)


class EventManager(ABC):
    def __init__(
        self,
        service: str,
        base_topic_prefix: str,
        logger: BoundLogger | None = None,
    ) -> None:
        self._service = service
        self._topic_prefix = f"{base_topic_prefix}.{service}"
        self._logger = logger or structlog.get_logger("metrics_event_manager")
        self._events: dict[str, Publisher] = {}
        self._registered = False

        # Not used in no-op
        self._broker: KafkaBroker
        self._manage_broker: bool
        self._admin_client: AIOKafkaAdminClient
        self._manage_admin_client: bool
        self._schema_manager: PydanticSchemaManager

    def create_publisher(
        self, payload_model: type[P], name: str | None = None
    ) -> Publisher[P]:
        if self._registered:
            raise RuntimeError(
                "All events must be registered before ``register_events`` is"
                " called"
            )
        payload_model.validate_structure()
        name = name or payload_model.__name__

        if name in self._events:
            raise RuntimeError(
                f"{name}: you have already created an event with this name."
                " Events must have unique names within this application."
            )
        event = Publisher(
            name=name,
            topic=f"{self._topic_prefix}.{name}",
            payload_model=payload_model,
            namespace=self._topic_prefix,
            manager=self,
        )

        self._events[name] = event
        return event

    @abstractmethod
    async def register_events(
        self,
        *,
        kafka_broker: KafkaBroker | KafkaConnectionSettings | None,
        kafka_admin_client: AIOKafkaAdminClient
        | KafkaConnectionSettings
        | None,
        schema_manager: PydanticSchemaManager | SchemaManagerSettings | None,
    ) -> None:
        self._registered = True

    async def aclose(self) -> None:
        return None

    @abstractmethod
    async def publish(
        self, event: Publisher, payload: Payload
    ) -> AvroBaseModel:
        if not self._registered:
            raise RuntimeError("``register`` must be called before publishing")
        time_ns = time.time_ns()
        metadata = EventMetadata(
            id=uuid4(),
            service=self._service,
            timestamp=self._ns_to_datetime(time_ns),
            timestamp_ns=time_ns,
        )
        return event.event_class(
            **metadata.model_dump(), **payload.model_dump()
        )

    def _ns_to_datetime(self, ns: int) -> datetime:
        return datetime.fromtimestamp(ns / 1e9, tz=UTC)


class NoopEventManager(EventManager):
    async def register_events(
        self,
        *,
        kafka_broker: KafkaBroker | KafkaConnectionSettings | None,
        kafka_admin_client: AIOKafkaAdminClient
        | KafkaConnectionSettings
        | None,
        schema_manager: PydanticSchemaManager | SchemaManagerSettings | None,
    ) -> None:
        await super().register_events(
            kafka_broker=kafka_broker,
            kafka_admin_client=kafka_admin_client,
            schema_manager=schema_manager,
        )

        self._logger.warning(
            "Called register on a no-op event manager. No events will"
            " actually be published."
        )

    async def publish(
        self, event: Publisher, payload: Payload
    ) -> AvroBaseModel:
        model = await super().publish(event, payload)
        self._logger.debug(
            "Would have published event",
            metrics_event=model.model_dump(),
        )
        return model


class RealEventManager(EventManager):
    async def register_events(
        self,
        *,
        kafka_broker: KafkaBroker | KafkaConnectionSettings | None,
        kafka_admin_client: AIOKafkaAdminClient
        | KafkaConnectionSettings
        | None,
        schema_manager: PydanticSchemaManager | SchemaManagerSettings | None,
    ) -> None:
        await super().register_events(
            kafka_broker=kafka_broker,
            kafka_admin_client=kafka_admin_client,
            schema_manager=schema_manager,
        )
        if (
            kafka_broker is None
            or kafka_admin_client is None
            or schema_manager is None
        ):
            raise RuntimeError(
                "This is not a no-op event manager, kafka_broker,"
                " kafka_admin_client, and schema_manager must not be None"
            )
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

        for event in self._events.values():
            await self._initialize_event(event)

    async def _initialize_event(self, event: Publisher) -> None:
        event.publisher = self._broker.publisher(
            event.topic, schema=event.event_class
        )

        topic = NewTopic(
            name=event.topic,
            num_partitions=1,
            replication_factor=3,
        )
        await self._admin_client.create_topics([topic])

        event.schema_info = await self._schema_manager.register_model(
            event.event_class
        )

    async def publish(
        self, event: Publisher, payload: Payload
    ) -> AvroBaseModel:
        model = await super().publish(event, payload)
        encoded = await self._schema_manager.serialize(model)
        await event.publisher.publish(encoded)

        self._logger.debug(
            "Published metrics event",
            metrics_event=model.model_dump(),
            topic=event.topic,
            schema_info=event.schema_info,
        )

        return model

    async def aclose(self) -> None:
        if self._manage_broker:
            await self._broker.close()
        if self._manage_admin_client:
            await self._admin_client.close()


def create_event_manager(
    *,
    service: str,
    base_topic_prefix: str,
    logger: BoundLogger | None = None,
    noop: bool = False,
) -> EventManager:
    if noop:
        return NoopEventManager(
            service=service, base_topic_prefix=base_topic_prefix, logger=logger
        )
    else:
        return RealEventManager(
            service=service, base_topic_prefix=base_topic_prefix, logger=logger
        )


def create_event_manager_from_config(
    config: MetricsConfiguration,
    logger: BoundLogger | None = None,
) -> EventManager:
    return create_event_manager(
        service=config.service,
        base_topic_prefix=config.base_topic_prefix,
        noop=config.noop,
        logger=logger,
    )
