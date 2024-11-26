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


class CaseInsensitiveFormMiddleware:
    """Make POST parameter keys all lowercase.

    This middleware attempts to work around case-sensitivity issues by
    lowercasing POST parameter keys before the request is processed. This
    allows normal FastAPI parsing to work without regard for case, permitting
    FastAPI to perform input validation on the POST parameters.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware with the ASGI application.

        Parameters
        ----------
        app
            The ASGI application to wrap.
        """
        self._app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process request set query parameters and POST body keys to
        lowercase.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        scope = copy(scope)

        if scope["method"] == "POST" and self.is_form_data(scope):
            receive = self.wrapped_receive(receive)

        await self._app(scope, receive, send)

    @staticmethod
    def is_form_data(scope: Scope) -> bool:
        """Check if the request contains form data.

        Parameters
        ----------
        scope
            The request scope.

        Returns
        -------
        bool
            True if the request contains form data, False otherwise.
        """
        headers = {
            k.decode("latin-1"): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        content_type = headers.get("content-type", "")
        return content_type.startswith("application/x-www-form-urlencoded")

    @staticmethod
    async def get_body(receive: Receive) -> bytes:
        """Read the entire request body.

        Parameters
        ----------
        receive
            The receive function to read messages from.

        Returns
        -------
        bytes
            The entire request body.
        """
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)
        return body

    @staticmethod
    async def process_form_data(body: bytes) -> bytes:
        """Process the body, lowercasing keys of form data.

        Parameters
        ----------
        body
            The request body.

        Returns
        -------
        bytes
            The processed request body with lowercased keys.
        """
        body_str = body.decode("utf-8")
        parsed = parse_qsl(body_str)
        lowercased = [(key.lower(), value) for key, value in parsed]
        processed = urlencode(lowercased)
        return processed.encode("utf-8")

    def wrapped_receive(self, receive: Receive) -> Receive:
        """Wrap the receive function to process form data.

        Parameters
        ----------
        receive
            The receive function to wrap.

        Returns
        -------
        Receive
            The wrapped receive function.
        """
        processed = False

        async def inner() -> dict:
            nonlocal processed
            if processed:
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }

            body = await self.get_body(receive)
            processed_body = await self.process_form_data(body)
            processed = True
            return {
                "type": "http.request",
                "body": processed_body,
                "more_body": False,
            }

        return inner
