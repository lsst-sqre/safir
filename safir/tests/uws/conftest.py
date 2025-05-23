"""pytest fixtures for UWS testing."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
import pytest_asyncio
import respx
import structlog
from asgi_lifespan import LifespanManager
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from structlog.stdlib import BoundLogger

from safir.arq import MockArqQueue
from safir.logging import configure_logging
from safir.middleware.x_forwarded import XForwardedMiddleware
from safir.slack.webhook import SlackRouteErrorHandler
from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook
from safir.testing.uws import MockUWSJobRunner, MockWobbly, patch_wobbly
from safir.uws import UWSApplication, UWSConfig
from safir.uws._dependencies import UWSFactory, uws_dependency

from ..support.uws import build_uws_config


@pytest_asyncio.fixture
async def app(
    arq_queue: MockArqQueue,
    mock_wobbly: MockWobbly,
    uws_config: UWSConfig,
    logger: BoundLogger,
) -> AsyncGenerator[FastAPI]:
    """Return a configured test application for UWS.

    This is a stand-alone test application independent of any real web
    application so that the UWS routes can be tested without reference to
    the pieces added by an application.
    """
    uws = UWSApplication(uws_config)
    uws.override_arq_queue(arq_queue)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        await uws.initialize_fastapi()
        yield
        await uws.shutdown_fastapi()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(XForwardedMiddleware)
    uws.install_middleware(app)
    router = APIRouter(route_class=SlackRouteErrorHandler)
    uws.install_handlers(router)
    app.include_router(router, prefix="/test")
    uws.install_error_handlers(app)

    async with LifespanManager(app):
        yield app


@pytest.fixture
def arq_queue() -> MockArqQueue:
    return MockArqQueue()


@pytest_asyncio.fixture
async def client(
    app: FastAPI, test_token: str, test_username: str
) -> AsyncGenerator[AsyncClient]:
    """Return an ``httpx.AsyncClient`` configured to talk to the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://example.com/",
        headers={
            "X-Auth-Request-Token": test_token,
            "X-Auth-Request-User": test_username,
        },
    ) as client:
        yield client


@pytest.fixture
def logger() -> BoundLogger:
    configure_logging(name="uws")
    return structlog.get_logger("uws")


@pytest.fixture(autouse=True)
def mock_google_storage() -> Iterator[MockStorageClient]:
    yield from patch_google_storage(
        expected_expiration=timedelta(minutes=15), bucket_name="some-bucket"
    )


@pytest.fixture(autouse=True)
def mock_slack(
    uws_config: UWSConfig, respx_mock: respx.Router
) -> MockSlackWebhook:
    assert uws_config.slack_webhook
    return mock_slack_webhook(
        uws_config.slack_webhook.get_secret_value(), respx_mock
    )


@pytest.fixture
def mock_wobbly(respx_mock: respx.Router, uws_config: UWSConfig) -> MockWobbly:
    return patch_wobbly(respx_mock, str(uws_config.wobbly_url))


@pytest_asyncio.fixture
async def runner(
    uws_config: UWSConfig, arq_queue: MockArqQueue
) -> MockUWSJobRunner:
    return MockUWSJobRunner(uws_config, arq_queue)


@pytest.fixture
def test_service() -> str:
    return "test-service"


@pytest.fixture
def test_token(test_service: str, test_username: str) -> str:
    return MockWobbly.make_token(test_service, test_username)


@pytest.fixture
def test_username() -> str:
    return "test-user"


@pytest.fixture
def uws_config() -> UWSConfig:
    return build_uws_config()


@pytest_asyncio.fixture
async def uws_factory(app: FastAPI, logger: BoundLogger) -> UWSFactory:
    return await uws_dependency(AsyncClient(), logger)
