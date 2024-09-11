"""Tools for working with metrics in non-production environments."""

from dataclasses import dataclass
from unittest.mock import AsyncMock

from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka import KafkaBroker

from ..schema_manager.pydantic_schema_manager import PydanticSchemaManager
from .event_manager import EventManagerStorage

__all__ = ["make_noop_storage"]


@dataclass
class NoopEventManagerStorage(EventManagerStorage):
    """A collection of no-op storage objects."""


def make_noop_storage() -> NoopEventManagerStorage:
    """Construct a collection of no-op storage objects."""
    mock_kafka_broker = AsyncMock(KafkaBroker)
    mock_kafka_broker.publisher.return_value = AsyncMock()

    return NoopEventManagerStorage(
        kafka_broker=mock_kafka_broker,
        kafka_admin_client=AsyncMock(AIOKafkaAdminClient),
        schema_manager=AsyncMock(PydanticSchemaManager),
    )
