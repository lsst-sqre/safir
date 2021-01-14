"""Tests for the safir.middleware module."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiohttp import web

from safir.logging import configure_logging
from safir.middleware import bind_logger

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture
    from aiohttp.pytest_plugin.test_utils import TestClient
    from aiohttp.web.web_response import Request, StreamResponse


async def test_bind_logger(
    aiohttp_client: TestClient, caplog: LogCaptureFixture
) -> None:
    """Test the bind_logger middleware.

    The procedure here is:

    1. Create an app and bind the middleware to it and configure logging.
    2. Call an endpoint on the app; that endpoint logs a Hello World message.
    3. Check the captured log output to ensure a log message with bound
       context was made.
    """

    async def handler(request: Request) -> StreamResponse:
        logger = request["safir/logger"]
        logger.info("Hello world")
        return web.Response(body="OK")

    @dataclass
    class Configuration:
        logger_name: str = "testapp"

    def create_app() -> web.Application:
        app = web.Application()
        app["safir/config"] = Configuration()
        configure_logging(name="testapp", profile="production")
        app.middlewares.append(bind_logger)
        app.router.add_route("GET", "/", handler)
        return app

    client = await aiohttp_client(create_app())
    response = await client.get("/")
    assert response.status == 200

    logger_name, logger_level, message = caplog.record_tuples[0]
    message_data = json.loads(message)
    assert message_data["event"] == "Hello world"
    # These keys got added specifically by the bind_logger middleware
    assert message_data["path"] == "/"
    assert message_data["method"] == "GET"
