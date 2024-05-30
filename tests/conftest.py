"""Test fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import pytest
import pytest_asyncio
import redis.asyncio as redis
import respx

from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook


@pytest.fixture
def database_url() -> str:
    """Dynamically construct the test database URL from tox-docker envvars."""
    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_5432_TCP_PORT"]
    return f"postgresql://safir@{host}:{port}/safir"


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


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[redis.Redis]:
    """Redis client for testing.

    This fixture connects to the Redis server that runs via tox-docker.
    """
    host = os.environ["REDIS_HOST"]
    port = os.environ["REDIS_6379_TCP_PORT"]
    client = redis.Redis(host=host, port=int(port), db=0)
    yield client

    await client.aclose()
