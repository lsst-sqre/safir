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

    The last three pieces of information will be added using naming consistent
    with the expectations of Google Log Explorer so that the request
    information will be liftedn into the appropriate JSON fields for complex
    log queries.
    """

    def __init__(self) -> None:
        self.logger: Optional[BoundLogger] = None

    async def __call__(self, request: Request) -> BoundLogger:
        """Return a logger bound with request information.

        Returns
        -------
        structlog.stdlib.BoundLogger
            The bound logger.
        """
        if not self.logger:
            self.logger = structlog.get_logger(logging.logger_name)
        assert self.logger

        # Construct the httpRequest logging data (compatible with the format
        # expected by Google Log Explorer).
        request_data = {
            "requestMethod": request.method,
            "requestUrl": str(request.url),
        }
        if request.client:
            request_data["remoteIp"] = request.client.host
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
