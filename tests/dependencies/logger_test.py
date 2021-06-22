"""Test the logger FastAPI dependency."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Dict
from unittest.mock import ANY

import pytest
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from safir.dependencies.logger import logger_dependency
from safir.logging import configure_logging

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture


@pytest.mark.asyncio
async def test_logger(caplog: LogCaptureFixture) -> None:
    configure_logging(name="myapp", profile="production", log_level="info")

    app = FastAPI()

    @app.get("/")
    async def handler(
        logger: BoundLogger = Depends(logger_dependency),
    ) -> Dict[str, str]:
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
        "level": "info",
        "logger": "myapp",
        "method": "GET",
        "param": "value",
        "path": "/",
        "remote": "127.0.0.1",
        "request_id": ANY,
        "user_agent": "some-user-agent/1.0",
    }
