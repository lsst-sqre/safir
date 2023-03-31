"""Test the Gafaelfawr auth FastAPI dependencies."""

from __future__ import annotations

import json
from unittest.mock import ANY

import pytest
from _pytest.logging import LogCaptureFixture
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from safir.dependencies.gafaelfawr import (
    auth_dependency,
    auth_logger_dependency,
)
from safir.logging import configure_logging


@pytest.mark.asyncio
async def test_auth_dependency() -> None:
    app = FastAPI()

    @app.get("/")
    async def handler(user: str = Depends(auth_dependency)) -> dict[str, str]:
        return {"user": user}

    async with AsyncClient(app=app, base_url="https://example.com") as client:
        r = await client.get("/")
        assert r.status_code == 422

        r = await client.get("/", headers={"X-Auth-Request-User": "someuser"})
        assert r.status_code == 200
        assert r.json() == {"user": "someuser"}


@pytest.mark.asyncio
async def test_auth_logger_dependency(caplog: LogCaptureFixture) -> None:
    configure_logging(name="myapp", profile="production", log_level="info")

    app = FastAPI()

    @app.get("/")
    async def handler(
        logger: BoundLogger = Depends(auth_logger_dependency),
    ) -> dict[str, str]:
        logger.info("something")
        return {}

    caplog.clear()
    async with AsyncClient(app=app, base_url="https://example.com") as client:
        r = await client.get("/", headers={"User-Agent": ""})
        assert r.status_code == 422

        r = await client.get(
            "/", headers={"User-Agent": "", "X-Auth-Request-User": "someuser"}
        )
        assert r.status_code == 200

    assert len(caplog.record_tuples) == 1
    assert json.loads(caplog.record_tuples[0][2]) == {
        "event": "something",
        "httpRequest": {
            "requestMethod": "GET",
            "requestUrl": "https://example.com/",
            "remoteIp": "127.0.0.1",
        },
        "logger": "myapp",
        "request_id": ANY,
        "severity": "info",
        "user": "someuser",
    }
