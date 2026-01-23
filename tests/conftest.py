"""Test fixtures."""

from __future__ import annotations

from collections.abc import (
    AsyncGenerator,
    Callable,
    Generator,
    Iterator,
    Sequence,
)
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import respx
import structlog
from aiokafka.admin.client import NewTopic
from arq.connections import ArqRedis, RedisSettings
from arq.constants import expires_extra_ms
from arq.cron import CronJob
from arq.jobs import Deserializer, Serializer
from arq.typing import SecondsTimedelta, StartupShutdown, WorkerCoroutine
from arq.worker import Function, Worker
from redis.asyncio import Redis
from structlog.testing import LogCapture
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from safir.kafka import FastStreamErrorHandler
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
from safir.testing.data import Data
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


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-test-data",
        action="store_true",
        default=False,
        help="Overwrite expected test output with current results",
    )


@pytest.fixture
def log_output() -> LogCapture:
    """Capture Structlog logs to assert against."""
    return LogCapture()


@pytest.fixture(autouse=True)
def configure_structlog(log_output: LogCapture) -> None:
    structlog.configure(processors=[log_output])


@pytest.fixture
def data(request: pytest.FixtureRequest) -> Data:
    update = request.config.getoption("--update-test-data")
    return Data(Path(__file__).parent / "data", update_test_data=update)


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
    """Yield a metrics stack that is test-scoped.

    This is useful in tests where we want to start and stop kafka components as
    part of the test.
    """
    async with make_metrics_stack(
        kafka_stack=test_scoped_kafka_stack,
        kafka_clients=test_scoped_kafka_clients,
        kafka_max_batch_size=1,
    ) as stack:
        yield stack


@pytest.fixture
def faststream_error_handler() -> FastStreamErrorHandler:
    """Create a FastStreamErrorHandler instance.

    This can be used in a test function to configure Slack error reporting for
    a FastStream broker or router.
    """
    return FastStreamErrorHandler()


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


@pytest_asyncio.fixture
async def arq_redis(redis: RedisContainer) -> AsyncGenerator[ArqRedis]:
    """Create ArqRedis connected to the global redis container."""
    arq_redis_ = ArqRedis(
        host=redis.get_container_host_ip(),
        port=redis.get_exposed_port(6379),
    )
    await arq_redis_.flushall()
    yield arq_redis_
    await arq_redis_.aclose(close_connection_pool=True)


@pytest_asyncio.fixture
async def create_arq_worker(arq_redis: ArqRedis) -> AsyncGenerator[Callable]:
    """Make a function to make an arq worker connected to the global redis.

    This is the fixture in the arq tests:
    https://github.com/python-arq/arq/blob/main/tests/conftest.py
    """
    worker_: Worker | None = None

    def create(
        functions: Sequence[Function | WorkerCoroutine],
        *,
        queue_name: str | None = None,
        cron_jobs: Sequence[CronJob] | None = None,
        redis_settings: RedisSettings | None = None,
        redis_pool: ArqRedis | None = arq_redis,
        burst: bool = True,
        on_startup: StartupShutdown | None = None,
        on_shutdown: StartupShutdown | None = None,
        on_job_start: StartupShutdown | None = None,
        on_job_end: StartupShutdown | None = None,
        after_job_end: StartupShutdown | None = None,
        handle_signals: bool = True,
        job_completion_wait: int = 0,
        max_jobs: int = 10,
        job_timeout: SecondsTimedelta = 300,
        keep_result: SecondsTimedelta = 3600,
        keep_result_forever: bool = False,
        poll_delay: int = 0,
        queue_read_limit: int | None = None,
        max_tries: int = 5,
        health_check_interval: SecondsTimedelta = 3600,
        health_check_key: str | None = None,
        ctx: dict[Any, Any] | None = None,
        retry_jobs: bool = True,
        allow_abort_jobs: bool = False,
        max_burst_jobs: int = -1,
        job_serializer: Serializer | None = None,
        job_deserializer: Deserializer | None = None,
        expires_extra_ms: int = expires_extra_ms,
        timezone: timezone | None = None,
        log_results: bool = True,
    ) -> Worker:
        nonlocal worker_
        worker_ = Worker(
            functions=functions,
            queue_name=queue_name,
            cron_jobs=cron_jobs,
            redis_settings=redis_settings,
            redis_pool=redis_pool,
            burst=burst,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            on_job_start=on_job_start,
            on_job_end=on_job_end,
            after_job_end=after_job_end,
            handle_signals=handle_signals,
            job_completion_wait=job_completion_wait,
            max_jobs=max_jobs,
            job_timeout=job_timeout,
            keep_result=keep_result,
            keep_result_forever=keep_result_forever,
            poll_delay=poll_delay,
            queue_read_limit=queue_read_limit,
            max_tries=max_tries,
            health_check_interval=health_check_interval,
            health_check_key=health_check_key,
            ctx=ctx,
            retry_jobs=retry_jobs,
            allow_abort_jobs=allow_abort_jobs,
            max_burst_jobs=max_burst_jobs,
            job_serializer=job_serializer,
            job_deserializer=job_deserializer,
            expires_extra_ms=expires_extra_ms,
            timezone=timezone,
            log_results=log_results,
        )
        return worker_

    yield create

    if worker_:
        await worker_.close()


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
    """Mock sentry transport and add custom exception info."""
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
