from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchemaRegistryConnectionSettings(BaseSettings):
    """Settings for connecting to a confluent-compatible schema registry."""

    url: AnyUrl = Field(
        ..., title="URL", description="URL for the schema registry"
    )

    model_config = SettingsConfigDict(
        env_prefix="SCHEMA_REGISTRY_", case_sensitive=False
    )
