from typing import TypedDict

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "SchemaManagerSettings",
    "SchemaRegistryClientParams",
    "SchemaRegistryConnectionSettings",
]


class SchemaRegistryClientParams(TypedDict):
    """Kwargs used to construct an AsyncSchemaRegistryClient."""

    url: str


class SchemaRegistryConnectionSettings(BaseSettings):
    """Settings for connecting to a confluent-compatible schema registry."""

    url: AnyUrl = Field(title="URL", description="URL for the schema registry")

    @property
    def schema_registry_client_params(self) -> SchemaRegistryClientParams:
        """Return kwargs to instantiate an AsyncSchemaRegistryClient."""
        return {"url": str(self.url)}

    model_config = SettingsConfigDict(
        env_prefix="SCHEMA_REGISTRY_", case_sensitive=False
    )


class SchemaManagerSettings(BaseSettings):
    """Settings for constructing a PydanticSchemaManager."""

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
        env_prefix="SCHEMA_MANAGER_", case_sensitive=False
    )
