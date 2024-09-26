from typing import TypedDict

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "SchemaManagerSettings",
    "SchemaRegistryClientParams",
]


class SchemaRegistryClientParams(TypedDict):
    """Kwargs used to construct an AsyncSchemaRegistryClient."""

    url: str
    """URL of a a Confluent-compatible schema registry."""


class SchemaManagerSettings(BaseSettings):
    """Settings for constructing a PydanticSchemaManager."""

    registry_url: AnyUrl = Field(
        title="Schema Registry URL",
        description="URL of a a Confluent-compatible schema registry.",
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

    def to_registry_params(self) -> SchemaRegistryClientParams:
        """Return kwargs to instantiate an AsyncSchemaRegistryClient."""
        return {"url": str(self.registry_url)}

    model_config = SettingsConfigDict(
        env_prefix="SCHEMA_MANAGER_", case_sensitive=False
    )
