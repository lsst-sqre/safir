"""Configuration for publishing events."""

from typing import Literal

from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka import KafkaBroker
from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from structlog.stdlib import BoundLogger

from ..kafka import (
    KafkaConnectionSettings,
    SchemaManagerSettings,
    SecurityProtocol,
)
from ._constants import ADMIN_CLIENT_PREFIX, BROKER_PREFIX
from ._event_manager import EventManager

__all__ = [
    "KafkaMetricsConfigurationDisabled",
    "KafkaMetricsConfigurationEnabled",
    "MetricsConfiguration",
]


class MetricsConfiguration(BaseSettings):
    """Configuration for emitting metrics."""

    topic_prefix: str = Field(
        "lsst.square.metrics.events",
        title="Metrics topic prefix",
        description=(
            "You probably should use the default here. It could be useful in"
            " development scenarios to change this."
        ),
    )

    app_name: str = Field(
        ...,
        title="Application name",
        description=(
            "The name of the application that is emitting these metrics"
        ),
    )

    disable: bool = Field(
        default=False,
        title="Disable",
        description='Set to "True" to prevent actually publishing metrics',
    )

    model_config = SettingsConfigDict(
        env_prefix="METRICS_", case_sensitive=False
    )


class KafkaMetricsConfigurationDisabled(MetricsConfiguration):
    """A config model you can pass directly to an EventManager constructor.

    This may be easier to use if you don't need to use kafka, the schema
    manager, or the schema registry, in any other parts of your application.
    """

    disable: Literal[True]

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
        kafka_config = KafkaConnectionSettings(
            security_protocol=SecurityProtocol.PLAINTEXT,
            bootstrap_servers="kafka_disabled",
        )
        schema_manager_config = SchemaManagerSettings(
            registry_url=AnyUrl("https://schema_registry_disabled")
        )
        broker = KafkaBroker(
            client_id=f"{BROKER_PREFIX}-{self.app_name}",
            **kafka_config.to_faststream_params(),
        )
        admin_client = AIOKafkaAdminClient(
            client_id=f"{ADMIN_CLIENT_PREFIX}-{self.app_name}",
            **kafka_config.to_aiokafka_params(),
        )
        schema_manager = schema_manager_config.make_manager()

        return EventManager(
            app_name=self.app_name,
            base_topic_prefix=self.topic_prefix,
            kafka_broker=broker,
            kafka_admin_client=admin_client,
            schema_manager=schema_manager,
            manage_kafka=True,
            disable=self.disable,
            logger=logger,
        )


class KafkaMetricsConfigurationEnabled(MetricsConfiguration):
    """A config model you can pass directly to an EventManager constructor.

    This may be easier to use if you don't need to use kafka, the schema
    manager, or the schema registry, in any other parts of your application.
    """

    disable: Literal[False]

    schema_manager: SchemaManagerSettings = Field(
        default_factory=SchemaManagerSettings
    )

    kafka: KafkaConnectionSettings = Field(
        default_factory=KafkaConnectionSettings
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
            client_id=f"{BROKER_PREFIX}-{self.app_name}",
            **self.kafka.to_faststream_params(),
        )
        admin_client = AIOKafkaAdminClient(
            client_id=f"{ADMIN_CLIENT_PREFIX}-{self.app_name}",
            **self.kafka.to_aiokafka_params(),
        )
        schema_manager = self.schema_manager.make_manager()

        return EventManager(
            app_name=self.app_name,
            base_topic_prefix=self.topic_prefix,
            kafka_broker=broker,
            kafka_admin_client=admin_client,
            schema_manager=schema_manager,
            manage_kafka=True,
            disable=self.disable,
            logger=logger,
        )
