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

The default httpx timeout has proven too short in practice for calls to, for
example, GitHub for authorization verification. Increase the default to 20
seconds. Users of this dependency can always lower it if needed.
"""


class HTTPClientDependency:
    """Provides an ``httpx.AsyncClient`` as a dependency.

    Notes
    -----
    The application must call ``http_client_dependency.aclose()`` as part of a
    shutdown hook:

    .. code-block:: python

       @app.on_event("shutdown")
       async def shutdown_event() -> None:
           await http_client_dependency.aclose()
    """

    def __init__(self) -> None:
        self.http_client = httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT)

    def __call__(self) -> httpx.AsyncClient:
        """Return the cached ``httpx.AsyncClient``."""
        return self.http_client

    async def aclose(self) -> None:
        """Close the ``httpx.AsyncClient``.

        It is an error to use the dependency after this method has been
        called. It should only be called during application shutdown.
        """
        await self.http_client.aclose()


http_client_dependency = HTTPClientDependency()
"""The dependency that will return the HTTP client."""
