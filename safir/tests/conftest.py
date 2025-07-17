"""Test fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator, Iterator
from datetime import timedelta

import pytest
import pytest_asyncio
import respx
import structlog
from aiokafka.admin.client import NewTopic
from redis.asyncio import Redis
from structlog.testing import LogCapture
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from safir.metrics import (
    EventManager,
    EventsConfiguration,
    KafkaMetricsConfiguration,
)
from safir.sentry import (
    before_send_handler,
    fingerprint_env_handler,
    sentry_exception_handler,
)
from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes
from safir.testing.sentry import (
    Captured,
    capture_events_fixture,
    sentry_init_fixture,
)
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook

from .support.kafka import (
    KafkaClients,
    KafkaStack,
    make_kafka_clients,
    make_kafka_stack,
)
from .support.metrics import MetricsStack, make_metrics_stack


@pytest.fixture
def log_output() -> LogCapture:
    """Capture Structlog logs to assert against."""
    return LogCapture()


@pytest.fixture(autouse=True)
def configure_structlog(log_output: LogCapture) -> None:
    structlog.configure(processors=[log_output])


@pytest.fixture(scope="session")
def session_kafka_stack(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[KafkaStack]:
    kafka_cert_path = tmp_path_factory.mktemp("kafka-certs")
    with make_kafka_stack(kafka_cert_path=kafka_cert_path) as stack:
        yield stack


@pytest.fixture
def kafka_stack(
    session_kafka_stack: KafkaStack,
) -> KafkaStack:
    session_kafka_stack.kafka_container.reset()
    session_kafka_stack.schema_registry_container.reset()
    return session_kafka_stack


@pytest_asyncio.fixture
async def kafka_clients(
    kafka_stack: KafkaStack,
) -> AsyncGenerator[KafkaClients]:
    async with make_kafka_clients(kafka_stack) as clients:
        yield clients


@pytest_asyncio.fixture
async def event_manager(
    kafka_stack: KafkaStack,
) -> AsyncGenerator[EventManager]:
    """Provide an event manager and create a matching Kafka topic."""
    config = KafkaMetricsConfiguration(
        application="testapp",
        enabled=True,
        events=EventsConfiguration(topic_prefix="what.ever"),
        kafka=kafka_stack.kafka_connection_settings,
        schema_manager=kafka_stack.schema_manager_settings,
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


@pytest.fixture
def test_scoped_kafka_stack(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[KafkaStack]:
    kafka_cert_path = tmp_path_factory.mktemp("kafka-certs")
    with make_kafka_stack(
        kafka_cert_path=kafka_cert_path, constant_host_ports=True
    ) as stack:
        yield stack


@pytest_asyncio.fixture
async def test_scoped_kafka_clients(
    test_scoped_kafka_stack: KafkaStack,
) -> AsyncGenerator[KafkaClients]:
    async with make_kafka_clients(test_scoped_kafka_stack) as clients:
        yield clients


@pytest_asyncio.fixture
async def resiliency_metrics_stack(
    test_scoped_kafka_stack: KafkaStack,
    test_scoped_kafka_clients: KafkaClients,
) -> AsyncGenerator[MetricsStack]:
    async with make_metrics_stack(
        kafka_stack=test_scoped_kafka_stack,
        kafka_clients=test_scoped_kafka_clients,
        kafka_max_batch_size=1,
    ) as stack:
        yield stack


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
async def redis_client(redis: RedisContainer) -> AsyncGenerator[Redis]:
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


@pytest.fixture
def sentry_fingerprint_items(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Captured]:
    """Mock sentry transport and add env to event fingerprints."""
    with sentry_init_fixture() as init:
        init(
            environment="some_env",
            traces_sample_rate=1.0,
            before_send=fingerprint_env_handler,
        )
        events = capture_events_fixture(monkeypatch)
        yield events()


@pytest.fixture
def sentry_exception_items(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Captured]:
    """Mock sentry transport and add SentryException info."""
    with sentry_init_fixture() as init:
        init(
            environment="some_env",
            traces_sample_rate=1.0,
            before_send=sentry_exception_handler,
        )
        events = capture_events_fixture(monkeypatch)
        yield events()


@pytest.fixture
def sentry_combo_items(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Captured]:
    """Mock sentry transport and add all recommended before_send processing."""
    with sentry_init_fixture() as init:
        init(
            environment="some_env",
            traces_sample_rate=1.0,
            before_send=before_send_handler,
        )
        events = capture_events_fixture(monkeypatch)
        yield events()
