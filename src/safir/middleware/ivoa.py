"""Middleware for IVOA services."""

from collections.abc import Awaitable, Callable
from urllib.parse import urlencode

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

__all__ = ["CaseInsensitiveQueryMiddleware"]


class CaseInsensitiveQueryMiddleware(BaseHTTPMiddleware):
    """Make query parameter keys all lowercase.

    Unfortunately, several IVOA standards require that query parameters be
    case-insensitive, which is not supported by modern HTTP web frameworks.
    This middleware attempts to work around this by lowercasing the query
    parameter keys before the request is processed, allowing normal FastAPI
    query parsing to then work without regard for case.  This, in turn,
    permits FastAPI to perform input validation on GET parameters, which would
    otherwise only happen if the case used in the request happened to match
    the case used in the function signature.

    This unfortunately doesn't handle POST, so routes that accept POST will
    need to parse the POST data case-insensitively in the handler or a
    dependency.

    Based on `fastapi#826 <https://github.com/tiangolo/fastapi/issues/826>`__.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        params = [(k.lower(), v) for k, v in request.query_params.items()]
        request.scope["query_string"] = urlencode(params).encode()
        return await call_next(request)
