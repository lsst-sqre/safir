"""Tools for publishing events from appliactions for later analysis."""

from __future__ import annotations

import time
from abc import ABCMeta, abstractmethod
from datetime import UTC, datetime
from typing import Generic, TypeVar, cast
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

__all__ = [
    "EventManager",
    "EventPublisher",
    "KafkaEventManager",
    "KafkaEventPublisher",
    "NoopEventManager",
    "NoopEventPublisher",
]


class EventPublisher(Generic[P], metaclass=ABCMeta):
    """Interface for event publishers.

    Represents a generic publisher of application metrics events.

    Parameters
    ----------
    application
        Name of the application to include in events.
    event_class
        Fully-enriched class to which payloads will be converted before
        publication.
    """

    def __init__(self, application: str, event_class: type[P]) -> None:
        self._application = application
        self._event_class = event_class

    def construct_event(self, payload: P) -> P:
        """Construct the full event as it will be published.

        Parameters
        ----------
        pyaload
            Payload to publish.

        Returns
        -------
        EventPayload
            Enriched event model including generic metadata and Avro schema
            configuration.
        """
        time_ns = time.time_ns()
        metadata = EventMetadata(
            id=uuid4(),
            application=self._application,
            timestamp=self._ns_to_datetime(time_ns),
            timestamp_ns=time_ns,
        )
        return self._event_class(
            **metadata.model_dump(), **payload.model_dump()
        )

    @abstractmethod
    async def publish(self, payload: P) -> EventMetadata:
        """Publish an event payload.

        Parameters
        ----------
        payload
            Payload to publish.

        Returns
        -------
        EventMetadata
            Full, enriched-with-metadata event model that was published. This
            will be an object of a class derived from both the type of the
            payload and `~safir.metrics.EventMetadata`, but it is typed as the
            latter since that is the newly-added information that may be of
            interest to the caller and therefore the most likely to be
            accessed.
        """

    @staticmethod
    def _ns_to_datetime(ns: int) -> datetime:
        """Convert an `int` number of nanoseconds to a `~datetime.datetime`."""
        return datetime.fromtimestamp(ns / 1e9, tz=UTC)


class KafkaEventPublisher(EventPublisher, Generic[P]):
    """Publishes one type of event.

    You shouldn't need to instantiate instances of this class yourself.
    Instead, call `~safir.metrics.EventManager.create_publisher`. This object
    wraps a FastStream publisher, schema information, and the underlying event
    manager that will be used to publish events.

    Parameters
    ----------
    application
        Name of the application publishing events.
    manager
        The EventManager that will actually publish the event to Kafka
    event_class
        An ``AvroBaseModel`` with the fields from the payload,
        `~safir.metrics.EventMetadata`, and an inner ``Meta`` class with
        additional schema configuration.
    publisher
        FastStream publisher to use to publish the event to Kafka. This
        contains Kafka metadata, like the topic to publish to.
    schema_info
        Confluent schema information for this event type.
    """

    def __init__(
        self,
        *,
        application: str,
        manager: KafkaEventManager,
        event_class: type[AvroBaseModel],
        publisher: AsyncAPIDefaultPublisher,
        schema_info: SchemaInfo,
    ) -> None:
        super().__init__(application, event_class)
        self._manager = manager
        self._publisher = publisher
        self._schema_info = schema_info

    async def publish(self, payload: P) -> EventMetadata:
        event = self.construct_event(payload)
        await self._manager.publish(event, self._publisher, self._schema_info)
        return event


class NoopEventPublisher(EventPublisher, Generic[P]):
    """Event publisher that quietly does nothing.

    This is used in applications when event publishing is disabled, so that
    the parsing and conversion of the events is still tested (thus making
    application tests meaningful), but the event is not sent anywhere.
    """

    def __init__(
        self,
        application: str,
        event_class: type[AvroBaseModel],
        logger: BoundLogger,
    ) -> None:
        super().__init__(application, event_class)
        self._logger = logger

    async def publish(self, payload: P) -> EventMetadata:
        event = self.construct_event(payload)
        self._logger.debug(
            "Would have published event", metrics_event=event.model_dump()
        )
        return event


class EventManager(metaclass=ABCMeta):
    """Interface for a client for publishing application metrics events.

    This interface is implemented by the fully-functional
    `~safir.metrics.KafkaEventManager` and the disabled
    `~safir.metrics.NoopEventManager`. The latter is used when events
    publishing is disabled so that the rest of the application code doesn't
    need to change.

    Parameters
    ----------
    topic
        Kafka topic to which events will be published.
    logger
        Logger to use. The ``safir.metrics`` logger will be used if none is
        provided.

    Attributes
    ----------
    topic
        Kafka topic to which events will be published.
    logger
        Logger that subclasses should use. This should not be used outside of
        subclasses of this class.
    """

    def __init__(
        self,
        topic: str,
        logger: BoundLogger | None = None,
    ) -> None:
        self.topic = topic
        self.logger = logger or structlog.get_logger("safir.metrics")
        self._publishers: dict[str, EventPublisher] = {}
        self._initialized = False

    async def aclose(self) -> None:
        """Shut down any internal state or managed clients."""
        self._publishers = {}
        self._initialized = False

    @abstractmethod
    async def build_publisher_for_model(
        self, model: type[P]
    ) -> EventPublisher[P]:
        """Implementation-specific construction of the event publisher.

        This class must be overridden by child classes to do the
        implementation-specific work of constructing an appropriate child
        instance of `~safir.metrics.EventPublisher`.

        Parameters
        ----------
        model
            Enriched and configured model representing the event that will be
            published.

        Returns
        -------
        EventPublisher
            An appropriate event publisher implementation instance.
        """

    async def create_publisher(
        self, name: str, payload_model: type[P]
    ) -> EventPublisher[P]:
        """Create an `~safir.metrics.EventPublisher` for a type of event.

        The schema is registered with the schema manager when this method is
        called.

        Parameters
        ----------
        name
            Name of the event. This will be used as the name of the Avro
            schema and record and the name of the event in the event storage
            backend.
        payload_model
            A type derived from `~safir.metrics.EventPayload`. This defines
            the type of models that will be passed into the
            `~safir.metrics.EventPublisher.publish` method of the resulting
            publisher. The events as published will include the information in
            this model plus the fields of `~safir.metrics.EventMetadata`.

        Returns
        -------
        EventPublisher
            A publisher for a type of event matching the ``payload_model``.

        Raises
        ------
        DuplicateEventError
            Raised if a publisher with the same name was already registered.
        EventManagerUnintializedError
            Raised if the `initialize` method was not been called before
            calling this method.
        KafkaTopicError
            Raised if the topic for publishing events doesn't exist or we
            don't have access to it.
        """
        if not self._initialized:
            msg = "Initialize EventManager before creating event publishers"
            raise EventManagerUnintializedError(msg)
        if name in self._publishers:
            raise DuplicateEventError(name)

        # Mixin used to configure dataclasses-avroschema.
        class MetaBase(AvroBaseModel):
            class Meta:
                schema_name = name
                namespace = self.topic

        # Construct the event model.
        model = cast(
            type[P],
            create_model(
                "EventModel",
                __base__=(payload_model, EventMetadata, MetaBase),
            ),
        )

        # Validate the structure of the model. This verifies that it can be
        # serialized correctly and will raise an exception if it cannot be.
        model.validate_structure()

        # Build the publisher, store it to detect duplicates, and return it.
        publisher = await self.build_publisher_for_model(model)
        self._publishers[name] = publisher
        return publisher

    async def initialize(self) -> None:
        """Initialize any internal state or managed clients.

        This method must be called before calling
        `~safir.metrics.EventManager.create_publisher`.
        """
        self._initialized = True


class KafkaEventManager(EventManager):
    """A tool for publishing application metrics events.

    Events are published to Kafka as avro-serialized messages. The schemas for
    the messages are stored in a Confluent Schema Registry, and this
    EventManager will manage those schemas and throw an exception if the event
    payloads evolve in an incompatible way.

    Parameters
    ----------
    application
        Name of the application that is generating events.
    topic_prefix
        Kafka topic prefix for the metrics events topic for this application.
    kafka_broker
        Broker to use to publish events to Kafka.
    kafka_admin_client
        Admin client to Kafka used to check that it is prepared for event
        publishing. For example, it is used to check if the topic exists.
    schema_manager
        Client to the Confluent-compatible schema registry.
    manage_kafka
        If `True`, close the ``kafka_broker`` and ``kafka_admin_client`` when
        `~safir.metrics.EventManager.aclose` is called. If your app's only use
        of Kafka is to publish metrics events, then this should be `True`. If
        you have a FastStream app that already configures some of these
        clients, this should probably be `False`, and you should pass
        pre-configured clients in.
    logger
        Logger to use for internal logging.

    Examples
    --------
    .. code-block:: python

       from safir.kafka import KafkaConnectionSettings, SchemaManagerSettings
       from safir.metrics import (
           EventsConfiguration,
           EventPayload,
           KafkaMetricsConfiguration,
       )


       config = KafkaMetricsConfiguration(
           events=EventsConfiguration(
               application="myapp",
               topic_prefix="what.ever",
           ),
           kafka=KafkaConnectionSettings(
               bootstrap_servers="someserver:1234",
               security_protocol=KafkaSecurityProtocol.PLAINTEXT,
           ),
           schema_manager=SchemaRegistryConnectionSettings(
               registry_url=AnyUrl("https://some.registry")
           ),
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
        application: str,
        topic_prefix: str,
        kafka_broker: KafkaBroker,
        kafka_admin_client: AIOKafkaAdminClient,
        schema_manager: PydanticSchemaManager,
        manage_kafka: bool = False,
        logger: BoundLogger | None = None,
    ) -> None:
        super().__init__(f"{topic_prefix}.{application}", logger)
        self._application = application
        self._broker = kafka_broker
        self._admin_client = kafka_admin_client
        self._schema_manager = schema_manager
        self._manage_kafka = manage_kafka

    async def aclose(self) -> None:
        """Clean up the Kafka clients if they are managed."""
        if self._manage_kafka:
            await self._broker.close()
            await self._admin_client.close()
        await super().aclose()

    async def build_publisher_for_model(
        self, model: type[P]
    ) -> EventPublisher[P]:
        """Build a Kafka publisher for a specific enriched model.

        Parameters
        ----------
        model
            Enriched and configured model representing the event that will be
            published.

        Returns
        -------
        EventPublisher
            An appropriate event publisher implementation instance.
        """
        async_publisher = self._broker.publisher(self.topic, schema=model)

        # Verify that the topic exists.
        if not await self._is_topic_ok(self.topic):
            raise KafkaTopicError(self.topic)

        # Register the Avro schema if necessary and get the schema details.
        schema_info = await self._schema_manager.register_model(model)

        # Return the corresponding event publisher.
        return KafkaEventPublisher[P](
            application=self._application,
            event_class=model,
            publisher=async_publisher,
            manager=self,
            schema_info=schema_info,
        )

    async def initialize(self) -> None:
        """Initialize the Kafka clients if they are managed."""
        if self._manage_kafka:
            await self._broker.start()
            await self._admin_client.start()
        self._initialized = True

    async def publish(
        self,
        event: AvroBaseModel,
        publisher: AsyncAPIDefaultPublisher,
        schema_info: SchemaInfo | None,
    ) -> None:
        """Serialize an event to Avro and publish it to Kafka.

        This method should generally not be called directly. It will be called
        from `~safir.metrics.KafkaEventPublisher.publish`.

        Parameters
        ----------
        event
            Fully-enhanced event to publish.
        publisher
            FastStream publisher to use to publish the event.
        schema_info
            Confluent schema registry information about the event type.

        Raises
        ------
        EventManagerUnintializedError
            Raised if the `initialize` method was not been called before
            calling this method.
        """
        if not self._initialized:
            msg = "Initialize EventManager before creating event publishers"
            raise EventManagerUnintializedError(msg)
        encoded = await self._schema_manager.serialize(event)
        await publisher.publish(encoded, no_confirm=True)
        self.logger.debug(
            "Published metrics event",
            metrics_event=event.model_dump(),
            topic=publisher.topic,
            schema_info=schema_info,
        )

    async def _is_topic_ok(self, topic: str) -> bool:
        """Check whether the given Kafka topic is valid.

        Parameters
        ----------
        topic
            Kafka topic to check.

        Returns
        -------
        bool
            `True` if the Kafka topic is valid, `False` otherwise.
        """
        info = await self._admin_client.describe_topics([topic])
        if len(info) == 0:
            return False
        topic_info = info[0]
        error_code = topic_info.get("error_code", None)
        return error_code == 0


class NoopEventManager(EventManager):
    """An event manager that creates publishers that quietly do nothing.

    This is used as the implementation of `~safir.metrics.EventManager` when
    event publication is disabled. The event type registrations and event
    payloads are still verified to catch errors, but are then discarded.


    Parameters
    ----------
    application
        Name of the application that is generating events.
    topic_prefix
        Kafka topic prefix for the metrics events topic for this application.
    logger
        Logger to use for internal logging.
    """

    def __init__(
        self,
        application: str,
        topic_prefix: str,
        logger: BoundLogger | None = None,
    ) -> None:
        super().__init__(f"{topic_prefix}.{application}", logger)
        self._application = application

    async def build_publisher_for_model(
        self, model: type[P]
    ) -> EventPublisher[P]:
        """Build a no-op publisher for a specific enriched model.

        Parameters
        ----------
        model
            Enriched and configured model representing the event that will be
            published.

        Returns
        -------
        EventPublisher
            An appropriate event publisher implementation instance.
        """
        return NoopEventPublisher[P](self._application, model, self.logger)
