"""Test IVOA middleware."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

import pytest
import pytest_asyncio
from fastapi import FastAPI, Query, Request
from httpx import ASGITransport, AsyncClient

from safir.middleware.ivoa import (
    CaseInsensitiveFormMiddleware,
    CaseInsensitiveQueryMiddleware,
)


def build_app() -> FastAPI:
    """Construct a test FastAPI app with the middleware registered."""
    app = FastAPI()
    app.add_middleware(CaseInsensitiveQueryMiddleware)
    app.add_middleware(CaseInsensitiveFormMiddleware)

    @app.get("/")
    async def handler(param: str) -> dict[str, str]:
        return {"param": param}

    @app.get("/simple")
    async def simple_handler() -> dict[str, str]:
        return {"foo": "bar"}

    @app.get("/list")
    async def list_handler(
        param: Annotated[list[str], Query()],
    ) -> dict[str, list[str]]:
        return {"param": param}

    @app.post("/form-list")
    async def form_handler(request: Request) -> dict[str, list[str]]:
        form = await request.form()
        return {
            "param": [str(v) for v in form.getlist("param")],
            "received_keys": list(form.keys()),
        }

    return app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Test client fixture with the IVOA middleware configured."""
    app = build_app()
    transport = ASGITransport(app=app)
    base_url = "https://example.com"
    async with AsyncClient(transport=transport, base_url=base_url) as client:
        yield client


@pytest.mark.asyncio
async def test_single_query_param_case_insensitive(
    client: AsyncClient,
) -> None:
    """Test that single query parameters are handled case-insensitively."""
    # Test normal case
    r = await client.get("/", params={"param": "foo"})
    assert r.status_code == 200
    assert r.json() == {"param": "foo"}

    # Test uppercase parameter
    r = await client.get("/", params={"PARAM": "foo"})
    assert r.status_code == 200
    assert r.json() == {"param": "foo"}

    # Test mixed case parameter
    r = await client.get("/", params={"pARam": "foo"})
    assert r.status_code == 200
    assert r.json() == {"param": "foo"}


@pytest.mark.asyncio
async def test_query_param_error_handling(client: AsyncClient) -> None:
    """Test error handling for invalid query parameters."""
    r = await client.get("/", params={"paramX": "foo"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_simple_endpoint(client: AsyncClient) -> None:
    """Test endpoint with no parameters."""
    r = await client.get("/simple")
    assert r.status_code == 200
    assert r.json() == {"foo": "bar"}


@pytest.mark.asyncio
async def test_list_query_params_case_insensitive(client: AsyncClient) -> None:
    """Test that list query parameters are handled case-insensitively."""
    r = await client.get(
        "/list",
        params=[("param", "foo"), ("PARAM", "BAR"), ("parAM", "baZ")],
    )
    assert r.status_code == 200
    assert r.json() == {"param": ["foo", "BAR", "baZ"]}


@pytest.mark.asyncio
async def test_form_data_case_insensitive(client: AsyncClient) -> None:
    """Test that form data parameters are handled case-insensitively."""
    form_data = {"param": "foo", "PARAM": "BAR", "parAM": "baZ"}
    r = await client.post("/form-list", data=form_data)
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["param"] == ["foo", "BAR", "baZ"]
    assert all(key == "param" for key in response_data["received_keys"])


@pytest.mark.asyncio
async def test_empty_form_data(client: AsyncClient) -> None:
    """Test that the endpoint handles empty form data gracefully."""
    r = await client.post("/form-list", data={})
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["param"] == []
    assert response_data["received_keys"] == []
