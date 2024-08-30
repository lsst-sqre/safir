"""Test the HTTP client FastAPI dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import pytest
import respx
from asgi_lifespan import LifespanManager
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from safir.dependencies.http_client import http_client_dependency


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return ["example.com"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await http_client_dependency.aclose()


@pytest.mark.asyncio
async def test_http_client(respx_mock: respx.Router) -> None:
    app = FastAPI(lifespan=_lifespan)
    respx_mock.get("https://www.google.com").respond(200)

    @app.get("/")
    async def handler(
        http_client: Annotated[AsyncClient, Depends(http_client_dependency)],
    ) -> dict[str, str]:
        assert isinstance(http_client, AsyncClient)
        await http_client.get("https://www.google.com")
        return {}

    transport = ASGITransport(app=app)
    base_url = "https://example.com"
    async with LifespanManager(app):
        async with AsyncClient(transport=transport, base_url=base_url) as c:
            r = await c.get("/")
    assert r.status_code == 200
