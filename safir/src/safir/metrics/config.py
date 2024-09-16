"""Configuration for publishing events."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["MetricsConfiguration"]


class MetricsConfiguration(BaseSettings):
    """Configuration for emitting events."""

    base_topic_prefix: str = Field(
        "lsst.square.metrics", title="Metrics topic prefix"
    )

    service: str = Field(
        ...,
        title="Service name",
        description="The name of the service that is emitting these metrics",
    )

    noop: bool = Field(
        default=False,
        title="No-op",
        description='Set to "True" to prevent actually publishing metrics',
    )

    model_config = SettingsConfigDict(
        env_prefix="METRICS_", case_sensitive=False
    )
