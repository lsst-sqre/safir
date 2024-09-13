from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchemaRegistryConnectionSettings(BaseSettings):
    """Settings for connecting to a confluent-compatible schema registry."""

    url: AnyUrl = Field(title="URL", description="URL for the schema registry")

    model_config = SettingsConfigDict(
        env_prefix="SCHEMA_REGISTRY_", case_sensitive=False
    )


class SchemaManagerSettings(BaseSettings):
    """Settings for constructing a PydanticSchemaManager."""

    schema_registry: SchemaRegistryConnectionSettings = Field(
        default_factory=SchemaRegistryConnectionSettings,
        title="Schema registry connection",
        description=(
            "Connection settings for a confluent-compatible schema registry."
        ),
    )

    suffix: str = Field(
        default="",
        title="Prefix",
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
