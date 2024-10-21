"""Test metrics configuration."""

from __future__ import annotations

import pytest
from pydantic import Field
from pydantic_settings import BaseSettings

from safir.metrics import (
    DisabledMetricsConfiguration,
    KafkaEventManager,
    KafkaMetricsConfiguration,
    MetricsConfiguration,
    NoopEventManager,
    metrics_configuration_factory,
)


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
