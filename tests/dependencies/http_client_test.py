"""Test the HTTP client FastAPI dependency."""

from __future__ import annotations

import pytest
import respx
from asgi_lifespan import LifespanManager
from fastapi import Depends, FastAPI
from httpx import AsyncClient

from safir.dependencies.http_client import http_client_dependency


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return ["example.com"]


@pytest.mark.asyncio
async def test_http_client(respx_mock: respx.Router) -> None:
    app = FastAPI()
    respx_mock.get("https://www.google.com").respond(200)

    @app.get("/")
    async def handler(
        http_client: AsyncClient = Depends(http_client_dependency),
    ) -> dict[str, str]:
        assert isinstance(http_client, AsyncClient)
        await http_client.get("https://www.google.com")
        return {}

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        await http_client_dependency.aclose()

    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://example.com") as c:
            r = await c.get("/")
    assert r.status_code == 200
