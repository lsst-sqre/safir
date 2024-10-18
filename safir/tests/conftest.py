"""Test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
import respx
from aiokafka import AIOKafkaConsumer
from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from faststream.kafka import KafkaBroker
from pydantic import AnyUrl
from redis.asyncio import Redis
from testcontainers.core.container import Network
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from safir.kafka import (
    KafkaConnectionSettings,
    PydanticSchemaManager,
    SchemaManagerSettings,
    SecurityProtocol,
)
from safir.metrics import (
    EventManager,
    EventsConfiguration,
    KafkaMetricsConfiguration,
)
from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook

from .support.kafka.container import FullKafkaContainer
from .support.schema_registry import SchemaRegistryContainer


@pytest.fixture(scope="session")
def kafka_docker_network() -> Iterator[Network]:
    """Provide a network object to link session-scoped testcontainers."""
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def kafka_cert_path(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    return tmp_path_factory.mktemp("kafka-certs")


@pytest.fixture(scope="session")
def global_kafka_container(
    kafka_docker_network: Network,
    kafka_cert_path: Path,
) -> Iterator[FullKafkaContainer]:
    """Provide a session-scoped kafka container.

    You proably want one of the dependent test-scoped fixtures that clears
    kafka data, like:
    * ``kafka_container``
    * ``kafka_broker``
    * ``kafka_consumer``
    * ``kafka_admin_client``
    """
    container = FullKafkaContainer(limit_broker_to_first_host=True)
    container.with_network(kafka_docker_network)
    container.with_network_aliases("kafka")
    with container as kafka:
        (kafka_cert_path / "ca.crt").write_text(
            container.get_secret_file_contents("ca.crt")
        )
        (kafka_cert_path / "client.crt").write_text(
            container.get_secret_file_contents("client.crt")
        )
        (kafka_cert_path / "client.key").write_text(
            container.get_secret_file_contents("client.key")
        )
        yield kafka


@pytest.fixture
def kafka_container(
    global_kafka_container: FullKafkaContainer,
) -> Iterator[FullKafkaContainer]:
    """Yield the global kafka container, but rid it of data post-test."""
    yield global_kafka_container
    global_kafka_container.reset()


@pytest.fixture
def kafka_connection_settings(
    kafka_container: FullKafkaContainer,
) -> KafkaConnectionSettings:
    """Provide a url to a session-scoped kafka container.

    All data is cleared from the kafka instance at the end of the test.
    """
    return KafkaConnectionSettings(
        bootstrap_servers=kafka_container.get_bootstrap_server(),
        security_protocol=SecurityProtocol.PLAINTEXT,
    )


@pytest_asyncio.fixture
async def kafka_consumer(
    kafka_connection_settings: KafkaConnectionSettings,
) -> AsyncIterator[AIOKafkaConsumer]:
    """Provide an AOIKafkaConsumer pointed at a session-scoped kafka container.

    All data is cleared from the kafka instance at the end of the test.
    """
    consumer = AIOKafkaConsumer(
        **kafka_connection_settings.to_aiokafka_params(),
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
    broker = KafkaBroker(
        **kafka_connection_settings.to_faststream_params(),
        client_id="pytest-broker",
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
    client = AIOKafkaAdminClient(
        **kafka_connection_settings.to_aiokafka_params(),
        client_id="pytest-admin",
    )
    await client.start()
    yield client
    await client.close()


@pytest.fixture(scope="session")
def global_schema_registry_container(
    global_kafka_container: FullKafkaContainer,
    kafka_docker_network: Network,
) -> Iterator[SchemaRegistryContainer]:
    """Provide a session-scoped schema registry container that can talk to the
    containers in other docker-based kafka fixtures.

    You probably want one of the dependent test-scoped fixtures that clears
    registry data, like ``schema_registry_connection_settings`` or
    ``schema_manager``.
    """
    container = SchemaRegistryContainer(network=kafka_docker_network)
    container.with_network(kafka_docker_network)
    container.with_network_aliases("schemaregistry")
    with container as schema_registry:
        yield schema_registry


@pytest.fixture
def schema_registry_container(
    global_schema_registry_container: SchemaRegistryContainer,
) -> Iterator[SchemaRegistryContainer]:
    """Yield the global schema registry container and rid of data post-test."""
    yield global_schema_registry_container
    global_schema_registry_container.reset()


@pytest.fixture
def schema_manager_settings(
    schema_registry_container: SchemaRegistryContainer,
) -> SchemaManagerSettings:
    """Provide a URL to a session-scoped schema registry.

    All data is cleared from it at the end of the test.
    """
    return SchemaManagerSettings(
        registry_url=AnyUrl(schema_registry_container.get_url())
    )


@pytest_asyncio.fixture
def schema_manager(
    schema_manager_settings: SchemaManagerSettings,
) -> PydanticSchemaManager:
    """Provide a PydanticSchemaManager pointed at a session-scoped schema
    registry container.

    All data is cleared from the registry at the end of the test.
    """
    return schema_manager_settings.make_manager()


@pytest_asyncio.fixture
async def event_manager(
    kafka_connection_settings: KafkaConnectionSettings,
    schema_manager_settings: SchemaManagerSettings,
) -> AsyncIterator[EventManager]:
    """Provide an event manager and create a matching Kafka topic."""
    config = KafkaMetricsConfiguration(
        application="testapp",
        enabled=True,
        events=EventsConfiguration(topic_prefix="what.ever"),
        kafka=kafka_connection_settings,
        schema_manager=schema_manager_settings,
    )

    manager = config.make_manager()
    await manager.initialize()
    topic = NewTopic(
        name="what.ever.testapp",
        num_partitions=1,
        replication_factor=1,
    )
    await manager._admin_client.create_topics([topic])
    yield manager
    await manager.aclose()


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
