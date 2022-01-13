"""Logger dependency for FastAPI.

Provides a `structlog` logger as a FastAPI dependency.  The logger will
incorporate information from the request in its bound context.
"""

import uuid
from typing import Optional

import structlog
from fastapi import Request
from structlog.stdlib import BoundLogger

from safir import logging

__all__ = ["LoggerDependency", "logger_dependency"]


class LoggerDependency:
    """Provides a structlog logger configured with request information.

    The following additional information will be included:

    * A UUID for the request
    * The method and URL of the request
    * The IP address of the client
    * The ``User-Agent`` header of the request, if any.

    The results of `~safir.middleware.XForwardedMiddleware` will be honored if
    present. The last three pieces of information will be added using naming
    consistent with the expectations of Google Log Explorer so that the
    request information will be liftedn into the appropriate JSON fields for
    complex log queries.
    """

    def __init__(self) -> None:
        self.logger: Optional[BoundLogger] = None

    async def __call__(self, request: Request) -> BoundLogger:
        """Return a logger bound with request information.

        Returns
        -------
        logger : `structlog.stdlib.BoundLogger`
            The bound logger.
        """
        if not self.logger:
            self.logger = structlog.get_logger(logging.logger_name)
        assert self.logger

        # Construct the request URL, honoring X-Forwarded-* if the
        # XForwardedMiddleware is in use.
        if getattr(request.state, "forwarded_host", None):
            if request.state.forwarded_proto:
                proto = request.state.forwarded_proto
            else:
                proto = request.url.scheme
            if request.state.forwarded_host:
                host = request.state.forwarded_host
            else:
                host = request.url.hostname
            url = f"{proto}://{host}{request.url.path}"
            if request.url.query:
                url += "?" + request.url.query
        else:
            url = str(request.url)

        # Construct the httpRequest logging data (compatible with the format
        # expected by Google Log Explorer).
        request_data = {
            "requestMethod": request.method,
            "requestUrl": url,
            "remoteIp": request.client.host,
        }
        user_agent = request.headers.get("User-Agent")
        if user_agent:
            request_data["userAgent"] = user_agent

        logger = self.logger.new(
            httpRequest=request_data,
            request_id=str(uuid.uuid4()),
        )
        return logger


logger_dependency = LoggerDependency()
"""The dependency that will return the logger for the current request."""
