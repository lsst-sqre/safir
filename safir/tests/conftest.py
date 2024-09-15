"""Test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from typing import Any, Self

import httpx
import pytest
import pytest_asyncio
import respx
from aiokafka import AIOKafkaConsumer
from httpx import ReadError, RemoteProtocolError
from redis.asyncio import Redis
from testcontainers.core.container import (
    DockerContainer,
    Network,
    wait_container_is_ready,
)
from testcontainers.kafka import KafkaContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from safir.kafka.aiokafka_consumer import make_kafka_consumer
from safir.kafka.config import KafkaConnectionSettings, KafkaSecurityProtocol
from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook


class SchemaRegistryContainer(DockerContainer):
    def __init__(
        self,
        kafka_bootstrap_servers: str = "kafka:9092",
        image: str = "confluentinc/cp-schema-registry:7.6.0",
        **kwargs: dict[str, Any],
    ) -> None:
        super().__init__(image, **kwargs)
        self.port = 8081
        self.with_exposed_ports(self.port)
        self.with_env(
            "SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS",
            kafka_bootstrap_servers,
        )
        self.with_env("SCHEMA_REGISTRY_LISTENERS", "http://0.0.0.0:8081")
        self.with_env(
            "SCHEMA_REGISTRY_HOST_NAME", self.get_container_host_ip()
        )

    def start(self, *args: list[Any], **kwargs: dict[str, Any]) -> Self:
        super().start(*args, **kwargs)
        self.health()
        return self

    def get_url(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        return f"http://{host}:{port}"

    class HealthCheckError(Exception):
        pass

    @wait_container_is_ready(ReadError, RemoteProtocolError)
    def health(self) -> None:
        url = f"{self.get_url()}/subjects"
        httpx.get(url, timeout=5).raise_for_status()


@pytest.fixture(scope="session")
def kafka_docker_network() -> Iterator[Network]:
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def kafka_container(kafka_docker_network: Network) -> Iterator[KafkaContainer]:
    container = KafkaContainer()
    container.with_network(kafka_docker_network)
    container.with_network_aliases("kafka")
    with container as kafka:
        yield kafka


@pytest_asyncio.fixture
async def kafka_consumer(
    kafka_bootstrap_server: str,
) -> AsyncIterator[AIOKafkaConsumer]:
    kafka_settings = KafkaConnectionSettings(
        bootstrap_servers=kafka_bootstrap_server,
        security_protocol=KafkaSecurityProtocol.PLAINTEXT,
    )
    consumer = make_kafka_consumer(config=kafka_settings, client_id="pytest")
    await consumer.start()

    yield consumer

    await consumer.stop()


@pytest.fixture(scope="session")
def kafka_bootstrap_server(kafka_container: KafkaContainer) -> str:
    return kafka_container.get_bootstrap_server()


@pytest.fixture(scope="session")
def schema_registry_url(
    kafka_container: KafkaContainer,
    kafka_docker_network: Network,
) -> Iterator[str]:
    container = SchemaRegistryContainer(kafka_bootstrap_servers="kafka:9092")
    container.with_network(kafka_docker_network)
    container.with_network_aliases("schemaregistry")
    with container as schema_registry:
        yield schema_registry.get_url()


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
