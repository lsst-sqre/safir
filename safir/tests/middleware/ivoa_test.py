"""Test IVOA middleware."""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient

from safir.middleware.ivoa import CaseInsensitiveQueryMiddleware


def build_app() -> FastAPI:
    """Construct a test FastAPI app with the middleware registered."""
    app = FastAPI()
    app.add_middleware(CaseInsensitiveQueryMiddleware)
    return app


@pytest.mark.asyncio
async def test_case_insensitive() -> None:
    app = build_app()

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

    transport = ASGITransport(app=app)
    base_url = "https://example.com"
    async with AsyncClient(transport=transport, base_url=base_url) as client:
        r = await client.get("/", params={"param": "foo"})
        assert r.status_code == 200
        assert r.json() == {"param": "foo"}

        r = await client.get("/", params={"PARAM": "foo"})
        assert r.status_code == 200
        assert r.json() == {"param": "foo"}

        r = await client.get("/", params={"pARam": "foo"})
        assert r.status_code == 200
        assert r.json() == {"param": "foo"}

        r = await client.get("/", params={"paramX": "foo"})
        assert r.status_code == 422

        r = await client.get("/simple")
        assert r.status_code == 200
        assert r.json() == {"foo": "bar"}

        r = await client.get(
            "/list",
            params=[("param", "foo"), ("PARAM", "BAR"), ("parAM", "baZ")],
        )
        assert r.status_code == 200
        assert r.json() == {"param": ["foo", "BAR", "baZ"]}
