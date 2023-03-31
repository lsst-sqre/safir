"""Test the logger FastAPI dependency."""

from __future__ import annotations

import json
from unittest.mock import ANY

import pytest
from _pytest.logging import LogCaptureFixture
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from safir.dependencies.logger import logger_dependency
from safir.logging import configure_logging
from safir.middleware.x_forwarded import XForwardedMiddleware


@pytest.mark.asyncio
async def test_logger(caplog: LogCaptureFixture) -> None:
    configure_logging(name="myapp", profile="production", log_level="info")

    app = FastAPI()

    @app.get("/")
    async def handler(
        logger: BoundLogger = Depends(logger_dependency),
    ) -> dict[str, str]:
        logger.info("something", param="value")
        return {}

    caplog.clear()
    async with AsyncClient(app=app, base_url="http://example.com") as client:
        r = await client.get(
            "/", headers={"User-Agent": "some-user-agent/1.0"}
        )
    assert r.status_code == 200

    assert len(caplog.record_tuples) == 1
    assert json.loads(caplog.record_tuples[0][2]) == {
        "event": "something",
        "httpRequest": {
            "requestMethod": "GET",
            "requestUrl": "http://example.com/",
            "remoteIp": "127.0.0.1",
            "userAgent": "some-user-agent/1.0",
        },
        "logger": "myapp",
        "param": "value",
        "request_id": ANY,
        "severity": "info",
    }


@pytest.mark.asyncio
async def test_logger_xforwarded(caplog: LogCaptureFixture) -> None:
    configure_logging(name="myapp", profile="production", log_level="info")

    app = FastAPI()
    app.add_middleware(XForwardedMiddleware)

    @app.get("/")
    async def handler(
        logger: BoundLogger = Depends(logger_dependency),
    ) -> dict[str, str]:
        logger.info("something", param="value")
        return {}

    caplog.clear()
    async with AsyncClient(app=app, base_url="http://example.com") as client:
        r = await client.get(
            "/",
            headers={
                "Host": "foo.example.com",
                "User-Agent": "",
                "X-Forwarded-For": "10.10.10.10",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "foo.example.com",
            },
        )
    assert r.status_code == 200

    assert len(caplog.record_tuples) == 1
    assert json.loads(caplog.record_tuples[0][2]) == {
        "event": "something",
        "httpRequest": {
            "requestMethod": "GET",
            "requestUrl": "https://foo.example.com/",
            "remoteIp": "10.10.10.10",
        },
        "logger": "myapp",
        "param": "value",
        "request_id": ANY,
        "severity": "info",
    }
