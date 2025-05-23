"""Configuration for publishing events."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated, override

import structlog
from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka import KafkaBroker
from pydantic import AfterValidator, AliasChoices, Field, ValidationError
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict
from structlog.stdlib import BoundLogger

from ..kafka import KafkaConnectionSettings, SchemaManagerSettings
from ._constants import ADMIN_CLIENT_PREFIX, BROKER_PREFIX
from ._event_manager import (
    EventManager,
    KafkaEventManager,
    MockEventManager,
    NoopEventManager,
)

__all__ = [
    "BaseMetricsConfiguration",
    "DisabledMetricsConfiguration",
    "EventsConfiguration",
    "KafkaMetricsConfiguration",
    "MetricsConfiguration",
    "MockMetricsConfiguration",
    "metrics_configuration_factory",
]


class EventsConfiguration(BaseSettings):
    """Configuration for emitting events."""

    model_config = SettingsConfigDict(
        env_prefix="METRICS_", populate_by_name=True
    )

    topic_prefix: str = Field(
        "lsst.square.metrics.events",
        title="Metrics topic prefix",
        description=(
            "You probably should use the default here. It could be useful in"
            " development scenarios to change this."
        ),
        validation_alias=AliasChoices(
            "topicPrefix", "METRICS_EVENTS_TOPIC_PREFIX"
        ),
    )


def _require_bool(v: bool, wanted: bool) -> bool:  # noqa: FBT001
    """Pydantic validator to require a `bool` field have a particular value.

    Unfortunately, we cannot just use a `~typing.Literal` type because those
    effectively only work for strings. Conversion to other types is not done
    when the type is given as a literal, so we have to use this validator
    hack.
    """
    if v != wanted:
        raise ValueError(f"Input should be {wanted}")
    return v


class BaseMetricsConfiguration(BaseSettings, ABC):
    """Metrics configuration, including the required Kafka configuration.

    Currently, this only configures events, but if additional types of metrics
    are added in the future, that configuration will be added here.

    This is the recommended configuration approach if you don't need to use
    Kafka, the schema manager, or the schema registry in any other parts of
    your application. Applications that also use Kafka directly should instead
    create a `~safir.metrics.EventManager` with externally-managed Kafka
    clients.
    """

    model_config = SettingsConfigDict(populate_by_name=True)

    application: str = Field(
        ...,
        title="Application name",
        description=(
            "The name of the application that is emitting these metrics"
        ),
        validation_alias=AliasChoices("appName", "METRICS_APPLICATION"),
    )

    events: EventsConfiguration = Field(
        default_factory=EventsConfiguration,
        title="Events configuration",
    )

    @abstractmethod
    def make_manager(
        self,
        logger: BoundLogger | None = None,
        *,
        kafka_broker: KafkaBroker | None = None,
    ) -> EventManager:
        """Construct an `~safir.metrics.EventManager`.

        Parameters
        ----------
        logger
            Logger to use for internal logging. If not given, the
            ``safir.metrics`` logger will be used.
        kafka_broker
            Kafka broker to use. If not given, a new Kafka broker will be
            created and automatically closed when the event manager is closed.
            If a broker is provided, closing the event manager will have no
            effect on it and the caller is responsible for starting and
            closing it.

        Returns
        -------
        EventManager
            An event manager appropriate to the configuration.
        """


class DisabledMetricsConfiguration(BaseMetricsConfiguration):
    """Metrics configuration when metrics reporting is disabled."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    enabled: Annotated[
        bool, AfterValidator(lambda x: _require_bool(x, False))
    ] = Field(
        ...,
        title="Whether to send events",
        description=(
            "If set to false, no events will be sent and all calls to publish"
            " events will be no-ops."
        ),
        validation_alias=AliasChoices("enabled", "METRICS_ENABLED"),
    )

    @override
    def make_manager(
        self,
        logger: BoundLogger | None = None,
        *,
        kafka_broker: KafkaBroker | None = None,
    ) -> NoopEventManager:
        if not logger:
            logger = structlog.get_logger("safir.metrics")
        return NoopEventManager(
            self.application, self.events.topic_prefix, logger
        )


class MockMetricsConfiguration(BaseMetricsConfiguration):
    """Metrics configuration when metrics publishing is mocked."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    enabled: Annotated[
        bool, AfterValidator(lambda x: _require_bool(x, False))
    ] = Field(
        ...,
        title="Whether to send events",
        description=(
            "If set to false, no events will be sent and all calls to publish"
            " events will be no-ops."
        ),
        validation_alias=AliasChoices("enabled", "METRICS_ENABLED"),
    )

    mock: Annotated[bool, AfterValidator(lambda x: _require_bool(x, True))] = (
        Field(
            title="Mock publishers",
            description=(
                "If set to true, all event publishers will be"
                " unittest.mock.MagicMock instances which will record all"
                " calls to their publish methods."
            ),
            validation_alias=AliasChoices("mock", "METRICS_MOCK"),
        )
    )

    @override
    def make_manager(
        self,
        logger: BoundLogger | None = None,
        *,
        kafka_broker: KafkaBroker | None = None,
    ) -> MockEventManager:
        if not logger:
            logger = structlog.get_logger("safir.metrics")
        return MockEventManager(
            self.application, self.events.topic_prefix, logger
        )


class KafkaMetricsConfiguration(BaseMetricsConfiguration):
    """Metrics configuration when enabled, including Kafka configuration."""

    model_config = SettingsConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )

    enabled: Annotated[
        bool, AfterValidator(lambda x: _require_bool(x, True))
    ] = Field(
        True,
        title="Whether to send events",
        description=(
            "If set to false, no events will be sent and all calls to publish"
            " events will be no-ops."
        ),
        validation_alias=AliasChoices("enabled", "METRICS_ENABLED"),
    )

    kafka: KafkaConnectionSettings = Field(
        default_factory=KafkaConnectionSettings,
        title="Kafka connection settings",
    )

    schema_manager: SchemaManagerSettings = Field(
        default_factory=SchemaManagerSettings,
        title="Kafka schema manager settings",
    )

    @override
    def make_manager(
        self,
        logger: BoundLogger | None = None,
        *,
        kafka_broker: KafkaBroker | None = None,
    ) -> KafkaEventManager:
        manage_kafka_broker = kafka_broker is None
        if not kafka_broker:
            kafka_broker = KafkaBroker(
                client_id=f"{BROKER_PREFIX}-{self.application}",
                **self.kafka.to_faststream_params(),
            )
        kafka_admin_client = AIOKafkaAdminClient(
            client_id=f"{ADMIN_CLIENT_PREFIX}-{self.application}",
            **self.kafka.to_aiokafka_params(),
        )
        schema_manager = self.schema_manager.make_manager(logger=logger)

        return KafkaEventManager(
            application=self.application,
            topic_prefix=self.events.topic_prefix,
            kafka_broker=kafka_broker,
            kafka_admin_client=kafka_admin_client,
            schema_manager=schema_manager,
            manage_kafka_broker=manage_kafka_broker,
            logger=logger,
        )


type MetricsConfiguration = (
    MockMetricsConfiguration
    | DisabledMetricsConfiguration
    | KafkaMetricsConfiguration
)
"""Type to use for metrics configuration in the application config.

This will resolve to one of the various valid types of metrics configuration,
all of which support a `~safir.metrics.BaseMetricsConfiguration.make_manager`
method to create an `~safir.metrics.EventManager`.
"""


def metrics_configuration_factory() -> MetricsConfiguration:
    """Choose an appropriate metrics configuration based on the environment.

    This function is intended for use as the argument to the
    ``default_factory`` parameter to `pydantic.Field` for the application
    metrics configuration. It selects an appropriate metrics configuration
    based on which configuration class can be instantiated from the available
    environment variables. This is not necessary if the application
    configuration comes from a source such as YAML that specifies settings for
    the metrics configuration, since in that case Pydantic will correctly
    instantiate the correct settings model.

    Returns
    -------
    BaseMetricsConfiguration
        An appropriate metrics configuration.

    Raises
    ------
    pydantic.ValidationError
        Raised if none of the possible configurations have their required
        variables set.

    Examples
    --------
    .. code-block:: python

       from pydantic_settings import BaseSettings
       from safir.metrics import (
           MetricsConfiguration,
           metrics_configuration_factory,
       )


       class Config(BaseSettings):
           metrics: MetricsConfiguration = Field(
               default_factory=metrics_configuration_factory,
               title="Metrics configuration",
           )


       config = Config()
    """
    # When there are more possible configuration models, this code should
    # first try to instantiate all of the ones that require specific
    # environment variable settings to enable, and then finally
    # unconditionally try to return the default.
    try:
        return MockMetricsConfiguration()
    except ValidationError:
        try:
            return DisabledMetricsConfiguration()
        except ValidationError:
            return KafkaMetricsConfiguration()
