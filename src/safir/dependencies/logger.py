"""Logger dependency for FastAPI.

Provides a :py:mod:`structlog` logger as a FastAPI dependency.  The logger
will incorporate information from the request in its bound context.
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
    * The method and path of the request
    * The IP address of the client (as ``remote``)
    * The ``User-Agent`` header of the request, if any.
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
        logger = self.logger.new(
            request_id=str(uuid.uuid4()),
            path=request.url.path,
            method=request.method,
            remote=request.client.host,
        )
        user_agent = request.headers.get("User-Agent")
        if user_agent:
            logger = logger.bind(user_agent=user_agent)
        return logger


logger_dependency = LoggerDependency()
"""The dependency that will return the logger for the current request."""
