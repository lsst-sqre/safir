"""Middleware for IVOA services."""

from copy import copy
from urllib.parse import parse_qsl, urlencode

from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["CaseInsensitiveQueryMiddleware"]


class CaseInsensitiveQueryMiddleware:
    """Make query parameter keys all lowercase.

    Unfortunately, several IVOA standards require that query parameters be
    case-insensitive, which is not supported by modern HTTP web frameworks.
    This middleware attempts to work around this by lowercasing the query
    parameter keys before the request is processed, allowing normal FastAPI
    query parsing to then work without regard for case. This, in turn, permits
    FastAPI to perform input validation on GET parameters, which would
    otherwise only happen if the case used in the request happened to match
    the case used in the function signature.

    This unfortunately doesn't handle POST, so routes that accept POST will
    need to parse the POST data case-insensitively in the handler or a
    dependency.

    Based on `fastapi#826 <https://github.com/fastapi/fastapi/issues/826>`__.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or not scope.get("query_string"):
            await self._app(scope, receive, send)
            return
        scope = copy(scope)
        params = [(k.lower(), v) for k, v in parse_qsl(scope["query_string"])]
        scope["query_string"] = urlencode(params).encode()
        await self._app(scope, receive, send)
        return
