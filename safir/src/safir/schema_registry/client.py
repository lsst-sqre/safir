from schema_registry.client import AsyncSchemaRegistryClient

from safir.schema_registry.config import SchemaRegistryConnectionSettings


def make_schema_registry_client(
    config: SchemaRegistryConnectionSettings,
) -> AsyncSchemaRegistryClient:
    return AsyncSchemaRegistryClient(url=str(config.url.scheme))
