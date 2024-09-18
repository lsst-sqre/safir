"""Test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
import respx
from aiokafka import AIOKafkaConsumer
from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka.annotations import KafkaBroker
from pydantic import AnyUrl
from redis.asyncio import Redis
from testcontainers.core.container import Network
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from safir.kafka import (
    make_kafka_admin_client,
    make_kafka_broker,
    make_kafka_consumer,
)
from safir.kafka.config import KafkaConnectionSettings, KafkaSecurityProtocol
from safir.schema_manager.config import (
    SchemaManagerSettings,
    SchemaRegistryConnectionSettings,
)
from safir.schema_manager.pydantic_schema_manager import PydanticSchemaManager
from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook

from .support.experiment.kafka import FullKafkaContainer
from .support.kafka import NetworkedKafkaContainer
from .support.schema_registry import NetworkedSchemaRegistryContainer


@pytest.fixture(scope="session")
def kafka_docker_network() -> Iterator[Network]:
    """Provide a network object to link session-scoped testcontainers."""
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def full_kafka_container(
    kafka_docker_network: Network,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[FullKafkaContainer]:
    container = FullKafkaContainer(
        host_cert_path=tmp_path_factory.mktemp("certs")
    )
    with container as kafka:
        yield kafka


@pytest.fixture(scope="session")
def kafka_cert_path(
    full_kafka_container: FullKafkaContainer,
) -> Path:
    return full_kafka_container.get_cert_path()


@pytest.fixture(scope="session")
def kafka_ssl_bootstrap_server(
    full_kafka_container: FullKafkaContainer,
) -> str:
    return full_kafka_container.get_ssl_bootstrap_server()


@pytest.fixture(scope="session")
def kafka_container(
    kafka_docker_network: Network,
) -> Iterator[NetworkedKafkaContainer]:
    """Provide a session-scoped schema kafka container that can talk to the
    containers in other docker-based kafka fixtures.

    You proably want one of the dependent test-scoped fixtures that clears
    kafka data, like:
    * ``kafka_broker``
    * ``kafka_consumer``
    * ``kafka_admin_client``
    """
    container = NetworkedKafkaContainer(network=kafka_docker_network)
    with container as kafka:
        yield kafka


@pytest.fixture(scope="session")
def schema_registry_container(
    kafka_container: NetworkedKafkaContainer,
    kafka_docker_network: Network,
) -> Iterator[NetworkedSchemaRegistryContainer]:
    """Provide a session-scoped schema registry container that can talk to the
    containers in other docker-based kafka fixtures.

    You probably want one of the dependent test-scoped fixtures that clears
    registry data, like ``schema_registry_connection_settings`` or
    ``schema_manager``.
    """
    container = NetworkedSchemaRegistryContainer(network=kafka_docker_network)
    with container as schema_registry:
        yield schema_registry


@pytest_asyncio.fixture
async def kafka_consumer(
    kafka_connection_settings: KafkaConnectionSettings,
) -> AsyncIterator[AIOKafkaConsumer]:
    """Provide an AOIKafkaConsumer pointed at a session-scoped kafka container.

    All data is cleared from the kafka instance at the end of the test.
    """
    consumer = make_kafka_consumer(
        config=kafka_connection_settings,
        client_id="pytest-consumer",
    )
    await consumer.start()

    yield consumer

    await consumer.stop()


@pytest_asyncio.fixture
async def kafka_broker(
    kafka_connection_settings: KafkaConnectionSettings,
) -> AsyncIterator[KafkaBroker]:
    """Provide a fast stream KafkaBroker pointed at a session-scoped kafka
    container.

    All data is cleared from the kafka instance at the end of the test.
    """
    broker = make_kafka_broker(
        config=kafka_connection_settings, client_id="pytest-broker"
    )
    await broker.start()

    yield broker

    await broker.close()


@pytest_asyncio.fixture
async def kafka_admin_client(
    kafka_connection_settings: KafkaConnectionSettings,
) -> AsyncIterator[AIOKafkaAdminClient]:
    """Provide an AOIKafkaAdmin client pointed at a session-scoped kafka
    container.

    All data is cleared from the kafka instance at the end of the test.
    """
    client = make_kafka_admin_client(
        config=kafka_connection_settings, client_id="pytest-admin"
    )
    await client.start()

    yield client

    await client.close()


@pytest_asyncio.fixture
def schema_manager(
    schema_registry_connection_settings: SchemaRegistryConnectionSettings,
) -> Iterator[PydanticSchemaManager]:
    """Provide a PydanticSchemaManager pointed at a session-scoped schema
    registry container.

    All data is cleared from the registry at the end of the test.
    """
    config = SchemaManagerSettings(
        schema_registry=schema_registry_connection_settings
    )
    yield PydanticSchemaManager.from_config(config)


@pytest.fixture
def kafka_connection_settings(
    kafka_container: NetworkedKafkaContainer,
) -> Iterator[KafkaConnectionSettings]:
    """Provide a url to a session-scoped kafka container.

    All data is cleared from the kafka instance at the end of the test.
    """
    yield KafkaConnectionSettings(
        bootstrap_servers=kafka_container.get_bootstrap_server(),
        security_protocol=KafkaSecurityProtocol.PLAINTEXT,
    )
    kafka_container.reset()


@pytest.fixture
def schema_registry_connection_settings(
    schema_registry_container: NetworkedSchemaRegistryContainer,
) -> Iterator[SchemaRegistryConnectionSettings]:
    """Provide a URL to a session-scoped schema registry.

    All data is cleared from it at the end of the test.
    """
    yield SchemaRegistryConnectionSettings(
        url=AnyUrl(schema_registry_container.get_url())
    )
    schema_registry_container.reset()


@pytest.fixture(scope="session")
def database_password() -> str:
    return "INSECURE@%PASSWORD/"


@pytest.fixture(scope="session")
def database_url(database_password: str) -> Iterator[str]:
    """Start a PostgreSQL database and return a URL for it."""
    with PostgresContainer(
        driver="asyncpg", username="safir", password=database_password
    ) as postgres:
        yield postgres.get_connection_url()


@pytest.fixture
def mock_gcs() -> Iterator[MockStorageClient]:
    yield from patch_google_storage(
        expected_expiration=timedelta(hours=1), bucket_name="some-bucket"
    )


@pytest.fixture
def mock_kubernetes() -> Iterator[MockKubernetesApi]:
    yield from patch_kubernetes()


@pytest.fixture
def mock_slack(respx_mock: respx.Router) -> MockSlackWebhook:
    return mock_slack_webhook("https://example.com/slack", respx_mock)


@pytest.fixture(scope="session")
def redis() -> Iterator[RedisContainer]:
    """Start a Redis container."""
    with RedisContainer() as redis:
        yield redis


@pytest_asyncio.fixture
async def redis_client(redis: RedisContainer) -> AsyncIterator[Redis]:
    """Create a Redis client for testing.

    This must be done separately for each test since it's tied to the per-test
    event loop, and therefore must be separated from the session-shared Redis
    server container.
    """
    host = redis.get_container_host_ip()
    port = redis.get_exposed_port(6379)
    client = Redis(host=host, port=port, db=0)
    yield client
    await client.aclose()
