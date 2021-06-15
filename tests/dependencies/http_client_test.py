"""Test the HTTP client FastAPI dependency."""

from __future__ import annotations

from typing import Dict, List

import pytest
from asgi_lifespan import LifespanManager
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from pytest_httpx import HTTPXMock

from safir.dependencies.http_client import http_client_dependency


@pytest.fixture
def non_mocked_hosts() -> List[str]:
    return ["example.com"]


@pytest.mark.asyncio
async def test_http_client(httpx_mock: HTTPXMock) -> None:
    app = FastAPI()
    httpx_mock.add_response(url="https://www.google.com")

    @app.get("/")
    async def handler(
        http_client: AsyncClient = Depends(http_client_dependency),
    ) -> Dict[str, str]:
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
