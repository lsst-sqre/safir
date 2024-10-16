"""Configuration for publishing events."""

from __future__ import annotations

from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka import KafkaBroker
from pydantic import AliasChoices, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict
from structlog.stdlib import BoundLogger

from ..kafka import KafkaConnectionSettings, SchemaManagerSettings
from ._constants import ADMIN_CLIENT_PREFIX, BROKER_PREFIX
from ._event_manager import EventManager

__all__ = ["KafkaMetricsConfiguration", "MetricsConfiguration"]


class MetricsConfiguration(BaseSettings):
    """Configuration for emitting metrics."""

    topic_prefix: str = Field(
        "lsst.square.metrics.events",
        title="Metrics topic prefix",
        description=(
            "You probably should use the default here. It could be useful in"
            " development scenarios to change this."
        ),
        validation_alias=AliasChoices("topicPrefix", "METRICS_TOPIC_PREFIX"),
    )

    app_name: str = Field(
        ...,
        title="Application name",
        description=(
            "The name of the application that is emitting these metrics"
        ),
        validation_alias=AliasChoices("appName", "METRICS_APP_NAME"),
    )

    disable: bool = Field(
        default=False,
        title="Disable",
        description='Set to "True" to prevent actually publishing metrics',
    )

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix="METRICS_",
        populate_by_name=True,
    )


class KafkaMetricsConfiguration(BaseSettings):
    """A config model you can pass directly to an EventManager constructor.

    This may be easier to use if you don't need to use kafka, the schema
    manager, or the schema registry, in any other parts of your application.
    """

    metrics_events: MetricsConfiguration = Field(
        default_factory=MetricsConfiguration, title="Events configuration"
    )

    schema_manager: SchemaManagerSettings = Field(
        default_factory=SchemaManagerSettings,
        title="Kafka schema manager settings",
    )

    kafka: KafkaConnectionSettings = Field(
        default_factory=KafkaConnectionSettings,
        title="Kafka connection settings",
    )

    model_config = SettingsConfigDict(
        alias_generator=to_camel, populate_by_name=True
    )

    def make_manager(self, logger: BoundLogger | None = None) -> EventManager:
        """Construct an EventManager and all of it's Kafka dependencies.

        If your app doesn't use Kafka or the Schema Registry, this is a
        shortcut to getting a working event manager without having to manually
        construct all of the Kafka dependencies.

        Parameters
        ----------
        logger
            A logger to use for internal logging

        """
        broker = KafkaBroker(
            client_id=f"{BROKER_PREFIX}-{self.metrics_events.app_name}",
            **self.kafka.to_faststream_params(),
        )
        admin_client = AIOKafkaAdminClient(
            client_id=f"{ADMIN_CLIENT_PREFIX}-{self.metrics_events.app_name}",
            **self.kafka.to_aiokafka_params(),
        )
        schema_manager = self.schema_manager.make_manager()

        return EventManager(
            app_name=self.metrics_events.app_name,
            base_topic_prefix=self.metrics_events.topic_prefix,
            kafka_broker=broker,
            kafka_admin_client=admin_client,
            schema_manager=schema_manager,
            manage_kafka=True,
            disable=self.metrics_events.disable,
            logger=logger,
        )
