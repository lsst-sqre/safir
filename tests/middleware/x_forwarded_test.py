"""Test ``X-Forwarded-For`` middleware."""

from __future__ import annotations

from ipaddress import _BaseNetwork, ip_network
from typing import Optional

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient

from safir.middleware.x_forwarded import XForwardedMiddleware


def build_app(proxies: Optional[list[_BaseNetwork]] = None) -> FastAPI:
    """Construct a test FastAPI app with the middleware registered."""
    app = FastAPI()
    app.add_middleware(XForwardedMiddleware, proxies=proxies)
    return app


@pytest.mark.asyncio
async def test_ok() -> None:
    app = build_app([ip_network("11.0.0.0/8")])

    @app.get("/")
    async def handler(request: Request) -> dict[str, str]:
        assert request.client
        assert request.client.host == "10.10.10.10"
        assert request.state.forwarded_host == "foo.example.com"
        assert request.url == "https://foo.example.com/"
        return {}

    async with AsyncClient(app=app, base_url="http://example.com") as client:
        r = await client.get(
            "/",
            headers={
                "Host": "foo.example.com",
                "X-Forwarded-For": "10.10.10.10, 11.11.11.11",
                "X-Forwarded-Proto": "https, http",
                "X-Forwarded-Host": "foo.example.com",
            },
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_defaults() -> None:
    app = build_app()

    @app.get("/")
    async def handler(request: Request) -> dict[str, str]:
        assert request.client
        assert request.client.host == "192.168.0.1"
        assert request.state.forwarded_host == "foo.example.com"
        assert request.url == "http://example.com/"
        return {}

    async with AsyncClient(app=app, base_url="http://example.com") as client:
        r = await client.get(
            "/",
            headers={
                "X-Forwarded-For": ("1.1.1.1, 192.168.0.1"),
                "X-Forwarded-Proto": "https, http",
                "X-Forwarded-Host": "foo.example.com",
            },
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_no_forwards() -> None:
    app = build_app([ip_network("127.0.0.1")])

    @app.get("/")
    async def handler(request: Request) -> dict[str, str]:
        assert not request.state.forwarded_host
        assert request.client
        assert request.client.host == "127.0.0.1"
        assert request.url == "http://example.com/"
        return {}

    async with AsyncClient(app=app, base_url="http://example.com") as client:
        r = await client.get("/")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_all_filtered() -> None:
    app = build_app([ip_network("10.0.0.0/8")])

    @app.get("/")
    async def handler(request: Request) -> dict[str, str]:
        assert request.client
        assert request.client.host == "10.10.10.10"
        assert request.state.forwarded_host == "foo.example.com"
        assert request.url == "https://example.com/"
        return {}

    async with AsyncClient(app=app, base_url="http://example.com") as client:
        r = await client.get(
            "/",
            headers={
                "X-Forwarded-For": "10.10.10.10, 10.0.0.1",
                "X-Forwarded-Proto": "https, http",
                "X-Forwarded-Host": "foo.example.com",
            },
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_one_proto() -> None:
    app = build_app([ip_network("11.11.11.11")])

    @app.get("/")
    async def handler(request: Request) -> dict[str, str]:
        assert request.client
        assert request.client.host == "10.10.10.10"
        assert request.state.forwarded_host == "foo.example.com"
        assert request.url == "https://example.com/"
        return {}

    async with AsyncClient(app=app, base_url="http://example.com") as client:
        r = await client.get(
            "/",
            headers={
                "X-Forwarded-For": "10.10.10.10, 11.11.11.11",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "foo.example.com",
            },
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_no_proto_or_host() -> None:
    app = build_app([ip_network("11.11.11.11")])

    @app.get("/")
    async def handler(request: Request) -> dict[str, str]:
        assert not request.state.forwarded_host
        assert request.client
        assert request.client.host == "10.10.10.10"
        assert request.url == "http://example.com/"
        return {}

    async with AsyncClient(app=app, base_url="http://example.com") as client:
        r = await client.get(
            "/", headers={"X-Forwarded-For": "10.10.10.10, 11.11.11.11"}
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_too_many_headers() -> None:
    """Test handling of duplicate headers.

    HTTPX doesn't allow passing in duplicate headers, so we cannot test end to
    end.  Instead, test by generating a mock request and then calling the
    underling middleware functions directly.
    """
    state = {
        "type": "http",
        "headers": [
            ("X-Forwarded-For", "10.10.10.10"),
            ("X-Forwarded-For", "10.10.10.1"),
            ("X-Forwarded-Proto", "https"),
            ("X-Forwarded-Proto", "http"),
            ("X-Forwarded-Host", "example.org"),
            ("X-Forwarded-Host", "example.com"),
        ],
    }
    request = Request(state)
    app = FastAPI()
    middleware = XForwardedMiddleware(app, proxies=[ip_network("10.0.0.0/8")])
    assert middleware._get_forwarded_for(request) == []
    assert middleware._get_forwarded_proto(request) == []
    assert not middleware._get_forwarded_host(request)
