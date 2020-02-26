"""Tests for the safir.http module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from safir.http import init_http_session

if TYPE_CHECKING:
    from aiohttp.pytest_plugin.test_utils import TestClient


async def test_init_http_session(aiohttp_client: TestClient) -> None:
    """Test basic use of init_http_session."""

    def create_app() -> web.Application:
        app = web.Application()
        app.cleanup_ctx.append(init_http_session)
        return app

    app = create_app()
    # Need to create the client itself to "start up" the app
    await aiohttp_client(app)

    assert "safir/http_session" in app
