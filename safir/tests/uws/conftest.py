"""pytest fixtures for UWS testing."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

import pytest
import pytest_asyncio
import respx
import structlog
from asgi_lifespan import LifespanManager
from fastapi import APIRouter, Body, FastAPI
from httpx import ASGITransport, AsyncClient
from structlog.stdlib import BoundLogger

from safir.arq import MockArqQueue
from safir.logging import configure_logging
from safir.middleware.x_forwarded import XForwardedMiddleware
from safir.slack.webhook import SlackRouteErrorHandler
from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook
from safir.testing.uws import MockUWSJobRunner
from safir.uws import UWSApplication, UWSConfig, UWSJobParameter
from safir.uws._dependencies import UWSFactory, uws_dependency

from ..support.uws import build_uws_config


@pytest.fixture
def post_params_router() -> APIRouter:
    """Return a router that echoes the parameters passed in the request."""
    router = APIRouter()

    @router.post("/params")
    async def post_params(
        params: Annotated[list[UWSJobParameter], Body()],
    ) -> dict[str, list[dict[str, str]]]:
        return {
            "params": [
                {"id": p.parameter_id, "value": p.value} for p in params
            ]
        }

    return router


@pytest_asyncio.fixture
async def app(
    arq_queue: MockArqQueue,
    uws_config: UWSConfig,
    logger: BoundLogger,
    post_params_router: APIRouter,
) -> AsyncIterator[FastAPI]:
    """Return a configured test application for UWS.

    This is a stand-alone test application independent of any real web
    application so that the UWS routes can be tested without reference to
    the pieces added by an application.
    """
    uws = UWSApplication(uws_config)
    await uws.initialize_uws_database(logger, reset=True)
    uws.override_arq_queue(arq_queue)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await uws.initialize_fastapi()
        yield
        await uws.shutdown_fastapi()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(XForwardedMiddleware)
    uws.install_middleware(app)
    router = APIRouter(route_class=SlackRouteErrorHandler)
    uws.install_handlers(router)
    app.include_router(router, prefix="/test")
    app.include_router(post_params_router, prefix="/test")
    uws.install_error_handlers(app)

    async with LifespanManager(app):
        yield app


@pytest.fixture
def arq_queue() -> MockArqQueue:
    return MockArqQueue()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Return an ``httpx.AsyncClient`` configured to talk to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="https://example.com/",
        headers={"X-Auth-Request-Token": "sometoken"},
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


@pytest_asyncio.fixture
async def runner(
    uws_config: UWSConfig, arq_queue: MockArqQueue
) -> AsyncIterator[MockUWSJobRunner]:
    async with MockUWSJobRunner(uws_config, arq_queue) as runner:
        yield runner


@pytest.fixture
def uws_config(database_url: str, database_password: str) -> UWSConfig:
    return build_uws_config(database_url, database_password)


@pytest_asyncio.fixture
async def uws_factory(
    app: FastAPI, logger: BoundLogger
) -> AsyncIterator[UWSFactory]:
    async for factory in uws_dependency(logger):
        yield factory
