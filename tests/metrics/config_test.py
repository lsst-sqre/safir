"""Test metrics configuration."""

from __future__ import annotations

import pytest
from pydantic import Field
from pydantic_settings import BaseSettings

from safir.metrics import (
    DisabledMetricsConfiguration,
    EventsConfiguration,
    KafkaEventManager,
    KafkaMetricsConfiguration,
    MetricsConfiguration,
    MockEventManager,
    MockMetricsConfiguration,
    NoopEventManager,
    metrics_configuration_factory,
)
from tests.support.kafka import KafkaClients, KafkaStack


class Config(BaseSettings):
    metrics: MetricsConfiguration = Field(
        default_factory=metrics_configuration_factory
    )


def test_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METRICS_APPLICATION", "test")
    monkeypatch.setenv("METRICS_ENABLED", "false")

    config = Config()
    assert isinstance(config.metrics, DisabledMetricsConfiguration)
    manager = config.metrics.make_manager()
    assert isinstance(manager, NoopEventManager)


def test_disabled_extra() -> None:
    config = Config.model_validate(
        {
            "metrics": {
                "enabled": False,
                "application": "example",
                "events": {"topicPrefix": "lsst.square.metrics.events"},
                "schemaManager": {
                    "registryUrl": "https://example.com",
                    "suffix": "",
                },
            }
        }
    )
    assert isinstance(config.metrics, DisabledMetricsConfiguration)


def test_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METRICS_APPLICATION", "test")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    monkeypatch.setenv("METRICS_MOCK", "true")

    config = Config()
    assert isinstance(config.metrics, MockMetricsConfiguration)
    manager = config.metrics.make_manager()
    assert isinstance(manager, MockEventManager)


@pytest.mark.asyncio
async def test_kafka(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METRICS_APPLICATION", "test")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-1.sasquatch:9092")
    monkeypatch.setenv("SCHEMA_MANAGER_REGISTRY_URL", "https://example.com/")

    config = Config()
    assert isinstance(config.metrics, KafkaMetricsConfiguration)
    manager = config.metrics.make_manager()
    assert isinstance(manager, KafkaEventManager)


@pytest.mark.asyncio
async def test_kafka_unmanaged(
    kafka_stack: KafkaStack, kafka_clients: KafkaClients
) -> None:
    config = KafkaMetricsConfiguration(
        application="testapp",
        events=EventsConfiguration(topic_prefix="what.ever"),
        kafka=kafka_stack.kafka_connection_settings,
        schema_manager=kafka_stack.schema_manager_settings,
    )

    manager = config.make_manager(kafka_broker=kafka_clients.kafka_broker)
    assert isinstance(manager, KafkaEventManager)

    # Make sure that the manager doesn't close the broker.
    await manager.aclose()
    assert await manager._broker.ping(timeout=1)
