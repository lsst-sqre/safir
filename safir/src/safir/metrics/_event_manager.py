"""Tools for publishing events from appliactions for later analysis."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import uuid4

import structlog
from aiokafka.admin.client import AIOKafkaAdminClient
from dataclasses_avroschema.pydantic import AvroBaseModel
from faststream.kafka import KafkaBroker
from faststream.kafka.publisher.asyncapi import AsyncAPIDefaultPublisher
from pydantic import create_model
from structlog.stdlib import BoundLogger

from ..kafka import PydanticSchemaManager, SchemaInfo
from ._exceptions import (
    DuplicateEventError,
    EventManagerUnintializedError,
    KafkaTopicError,
)
from ._models import EventMetadata, EventPayload

P = TypeVar("P", bound=EventPayload)
"""Generic event payload type."""


__all__ = ["EventManager", "EventPublisher"]


class EventPublisher(Generic[P]):
    """Publishes one type of event.

    You shouldn't need to instantiate instances of this class yourself, they
    should be instantiated by an `~safir.metrics.EventManager`. This is a
    bucket to remember attributes and type information about one kind of event
    at initialization time, to later be used at publishing time in a type-safe
    way.

    Parameters
    ----------
    manager
        The EventManager that will actually publish the event to Kafka
    event_class
        An AvroBaseModel with the fields from the payload ``P``,
        ``EventMetadata``, and an inner ``Meta`` class with schema info
    publisher
        A FastStream publisher to publish the event to Kafka. This contains
        Kafka metadata, like the topic to publish to.
    """

    def __init__(
        self,
        *,
        manager: EventManager,
        event_class: type[AvroBaseModel],
        publisher: AsyncAPIDefaultPublisher,
        schema_info: SchemaInfo,
    ) -> None:
        self.manager = manager
        self.event_class = event_class
        self.publisher = publisher
        self.schema_info = schema_info

    async def publish(self, payload: P) -> AvroBaseModel:
        """Pass the payload and event info to the EventManager to publish.

        Parameters
        ----------
        Payload
            A subclass of EventPayload to be enriched with metadata and
            published to Kafka.

        Returns
        -------
        dataclasses_avroschema.pydantic.AvroBaseModel
            The full, enriched-with-metadata, event model that was published.
        """
        return await self.manager.publish(
            payload=payload,
            publisher=self.publisher,
            event_class=self.event_class,
            schema_info=self.schema_info,
        )


class EventManager:
    """A tool for publishing application metrics events.

    Events are published to Kafka as avro-serialized messages. The schemas for
    the messages are stored in a Confluent Schema Registry, and this
    EventManager will manage those schemas and throw an exception if the event
    payloads evolve in an incompatible way.


    Parameters
    ----------
    app_name
        The name of the application that is generating events
    base_topic_prefix
        The Kafka topic prefix for the metrics events topic for this
        application
    kafka_broker
        Does the Kafka publishing
    kafka_admin_client
        Ensures that Kafka is prepared for event publishing; that the topic
        exists, for example.
    schema_manager
        Handles all Confluent Schema Registry interactions
    manage_kafka
        If ``True``, close the ``kafka_broker`` and ``kafka_admin_client`` when
        ``aclose`` is called. If your app's only use of Kafka is to publish
        metrics events, then this should be ``True``. If you have a FastStream
        app that already configures some of these clients, this should probably
        be ``False``, and you should pass pre-configured clients in.
    disable
        If ``False``, don't actually do anything. No Kafka or Schema Registry
        interactions will happen. This is useful for running apps locally.
    logger
        A logger to use for internal logging

    Examples
    --------
    .. code-block:: python

       from safir.metrics import MetricsConfigurationWithKafka

       config = MetricsConfigurationWithKafka(
           metrics_events=MetricsConfiguration(
               app_name="myapp",
               base_topic_prefix="what.ever",
           ),
           kafka=KafkaConnectionSettings(
               bootstrap_servers="someserver:1234",
               security_protocol=KafkaSecurityProtocol.PLAINTEXT,
           ),
           schema_registry=SchemaRegistryConnectionSettings(
               url=AnyUrl("https://some.registry")
           ),
           schema_manager=SchemaManagerSettings(),
       )
       manager = config.make_manager()


       class MyEvent(EventPayload):
           foo: str


       publisher = manager.create_publisher(MyEvent)
       await manager.register_and_initialize()

       await publisher.publish(MyEvent(foo="bar1"))
       await publisher.publish(MyEvent(foo="bar2"))

       await manager.aclose()

    """

    def __init__(
        self,
        *,
        app_name: str,
        base_topic_prefix: str,
        kafka_broker: KafkaBroker,
        kafka_admin_client: AIOKafkaAdminClient,
        schema_manager: PydanticSchemaManager,
        manage_kafka: bool = False,
        disable: bool = False,
        logger: BoundLogger | None = None,
    ) -> None:
        self._app_name = app_name
        self._topic = f"{base_topic_prefix}.{app_name}"
        self._broker = kafka_broker
        self._admin_client = kafka_admin_client
        self._schema_manager = schema_manager
        self._manage_kafka = manage_kafka
        self._disable = disable
        self._logger = logger or structlog.get_logger("metrics_event_manager")

        self._publishers: dict[str, EventPublisher] = {}
        self._initialized = False

    async def create_publisher(
        self, name: str, payload_model: type[P]
    ) -> EventPublisher[P]:
        """Create an EventPublisher that can publish an event of type ``P``.

        All event publishers must be created with this method before
        ``register_and_initialize`` is called.

        Parameters
        ----------
        name
            The name of the event. This will be the name of the Avro schema and
            record, and the name of the event in the event storage backend.
        payload_model
            An ``EventPayload`` type. Instance of this type can be passed into
            the ``publish`` method of this publisher, and they will be
            published.

        Returns
        -------
        EventPublisher
            An object that can be used to publish events of type ``P``

        Raises
        ------
        DuplicateEventError
            Upon an attempt to register a publisher with the same name as one
            that was already registered.
        EventManagerUnintializedError
            Upon an attempt to create a publisher before calling ``initialize``
            on this ``EventManager`` instance.
        KafkaTopicError
            If the topic for publishing events doesn't exist, or we don't have
            access to it.
        """
        if not self._initialized:
            raise EventManagerUnintializedError(
                "EventManager instance must be initialized before creating"
                " event publishers"
            )

        if name in self._publishers:
            raise DuplicateEventError(name)
        payload_model.validate_structure()

        class MetaBase(AvroBaseModel):
            # Used by dataclasses-avroschema to set the avro name and namespace
            class Meta:
                schema_name = name
                namespace = self._topic

        # The full, metadata-enriched event model
        event_class = create_model(
            "EventModel",
            __base__=(payload_model, EventMetadata, MetaBase),
        )

        if not issubclass(event_class, AvroBaseModel):
            raise TypeError(
                "This can never happen, but mypy can't figure that out."
            )

        async_publisher = self._broker.publisher(
            self._topic, schema=event_class
        )

        publisher: EventPublisher[P]

        if self._disable:
            return EventPublisher(
                event_class=event_class,
                publisher=async_publisher,
                manager=self,
                schema_info=SchemaInfo(
                    schema=event_class.avro_schema_to_python(),
                    schema_id=0,
                    subject="disabled",
                ),
            )

        topic_info = await self._admin_client.describe_topics([self._topic])
        if not self._is_topic_ok(topic_info):
            raise KafkaTopicError(self._topic)

        schema_info = await self._schema_manager.register_model(event_class)

        publisher = EventPublisher(
            event_class=event_class,
            publisher=async_publisher,
            manager=self,
            schema_info=schema_info,
        )

        self._publishers[name] = publisher
        return publisher

    async def initialize(self) -> None:
        """Initialize Kafka clients (if this ``EventManager`` is managing
        them).
        """
        if self._disable:
            self._logger.warning(
                "Called register on a disabled event manager. No events will"
                " actually be published."
            )
            self._initialized = True
            return

        if self._manage_kafka:
            await self._broker.start()
            await self._admin_client.start()

        self._initialized = True

    def _is_topic_ok(self, info: list[Any]) -> bool:
        """Parse an ``AIOKafkaAdminClient.describe_topics`` response."""
        if len(info) == 0:
            return False
        topic_info = info[0]
        error_code = topic_info.get("error_code", None)
        return error_code == 0

    async def aclose(self) -> None:
        """Clean up the Kafka clients, if we're managing them."""
        if not self._disable and self._manage_kafka:
            await self._broker.close()
            await self._admin_client.close()

    async def publish(
        self,
        *,
        payload: EventPayload,
        publisher: AsyncAPIDefaultPublisher,
        event_class: type[AvroBaseModel],
        schema_info: SchemaInfo | None,
    ) -> AvroBaseModel:
        """Serialize an event to Avro and publish it to Kafka.

        You shouldn't call this method directly, it will usually be called from
        the ``publish`` method of an ``EventPublisher``.

        Raises
        ------
        EventManagerUnintializedError
            Upon an attempt to create a publisher before calling ``initialize``
            on this ``EventManager`` instance.

        """
        if not self._initialized:
            raise EventManagerUnintializedError(
                "EventManager instance must be initialized before creating"
                " event publishers"
            )

        time_ns = time.time_ns()
        metadata = EventMetadata(
            id=uuid4(),
            app_name=self._app_name,
            timestamp=self._ns_to_datetime(time_ns),
            timestamp_ns=time_ns,
        )
        event = event_class(**metadata.model_dump(), **payload.model_dump())

        if self._disable:
            self._logger.debug(
                "Would have published event",
                metrics_event=event.model_dump(),
            )
            return event

        encoded = await self._schema_manager.serialize(event)
        await publisher.publish(encoded)

        self._logger.debug(
            "Published metrics event",
            metrics_event=event.model_dump(),
            topic=publisher.topic,
            schema_info=schema_info,
        )

        return event

    def _ns_to_datetime(self, ns: int) -> datetime:
        """Convert a int number of nanoseconds to a datetime."""
        return datetime.fromtimestamp(ns / 1e9, tz=UTC)
