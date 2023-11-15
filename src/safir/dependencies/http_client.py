"""HTTP client dependency for FastAPI."""

from __future__ import annotations

import httpx

__all__ = [
    "DEFAULT_HTTP_TIMEOUT",
    "HTTPClientDependency",
    "http_client_dependency",
]

DEFAULT_HTTP_TIMEOUT = 20.0
"""Default timeout (in seconds) for outbound HTTP requests.

The default HTTPX timeout has proven too short in practice for calls to, for
example, GitHub for authorization verification. Increase the default to 20
seconds. Users of this dependency can always lower it if needed.
"""


class HTTPClientDependency:
    """Provides an ``httpx.AsyncClient`` as a dependency.

    The resulting client will have redirects enabled and the default timeout
    increased to 20 seconds.

    Notes
    -----
    The application must call ``http_client_dependency.aclose()`` in the
    application lifespan hook:

    .. code-block:: python

       from collections.abc import AsyncIterator
       from contextlib import asynccontextmanager

       from fastapi import FastAPI


       @asynccontextmanager
       async def lifespan(app: FastAPI) -> AsyncIterator[None]:
           yield
           await http_client_dependency.aclose()


       app = FastAPI(lifespan=lifespan)
    """

    def __init__(self) -> None:
        self.http_client: httpx.AsyncClient | None = None

    async def __call__(self) -> httpx.AsyncClient:
        """Return the cached ``httpx.AsyncClient``."""
        if not self.http_client:
            self.http_client = httpx.AsyncClient(
                timeout=DEFAULT_HTTP_TIMEOUT, follow_redirects=True
            )
        return self.http_client

    async def aclose(self) -> None:
        """Close the ``httpx.AsyncClient``."""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None


http_client_dependency = HTTPClientDependency()
"""The dependency that will return the HTTP client."""
