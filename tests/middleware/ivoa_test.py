"""Test IVOA middleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

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

    async with AsyncClient(app=app, base_url="https://example.com") as client:
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
