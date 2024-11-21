"""Configuration for the Kafka Schema Registry."""

from __future__ import annotations

from typing import TypedDict

from pydantic import AliasChoices, AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from schema_registry.client import AsyncSchemaRegistryClient
from structlog.stdlib import BoundLogger

from safir.kafka._manager import PydanticSchemaManager

__all__ = [
    "SchemaManagerSettings",
    "SchemaRegistryClientParams",
]


class SchemaRegistryClientParams(TypedDict):
    """Kwargs used to construct an AsyncSchemaRegistryClient."""

    url: str
    """URL of a a Confluent-compatible schema registry."""


class SchemaManagerSettings(BaseSettings):
    """Settings for constructing a `~safir.kafka.PydanticSchemaManager`."""

    registry_url: AnyUrl = Field(
        title="Schema registry URL",
        description="URL of a a Confluent-compatible schema registry",
        validation_alias=AliasChoices(
            "registryUrl", "SCHEMA_MANAGER_REGISTRY_URL"
        ),
    )

    suffix: str = Field(
        default="",
        title="Suffix",
        description=(
            "A suffix that is added to the schema name (and thus the subject"
            " name). The suffix creates alternate subjects in the Schema"
            " Registry so schemas registered during testing and staging don't"
            " affect the compatibility continuity of a production subject. For"
            " production, it's best to not set a suffix."
        ),
        examples=["_dev1"],
    )

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix="SCHEMA_MANAGER_",
        extra="forbid",
        populate_by_name=True,
    )

    def to_registry_params(self) -> SchemaRegistryClientParams:
        """Make a dict of params to construct an AsyncSchemaRegistryClient."""
        return {"url": str(self.registry_url)}

    def make_manager(
        self, logger: BoundLogger | None = None
    ) -> PydanticSchemaManager:
        """Construct a PydanticSchemaManager from the fields of this model."""
        registry = AsyncSchemaRegistryClient(**self.to_registry_params())
        return PydanticSchemaManager(
            registry=registry, suffix=self.suffix, logger=logger
        )
