"""Logger dependency for FastAPI.

Provides a `structlog` logger as a FastAPI dependency.  The logger will
incorporate information from the request in its bound context.
"""

import uuid

import structlog
from fastapi import Request
from structlog.stdlib import BoundLogger

_logger_name: str | None = None
"""Name of the configured global logger.

When `configure_logging` is called, the name of the configured logger is
stored in this variable. It is used by the logger dependency to retrieve the
application's configured logger.

Only one configured logger is supported. Additional calls to
`configure_logging` change the stored logger name.

This variable is internal to Safir and should not be used outside of the
library.
"""

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
        self.logger: BoundLogger | None = None

    async def __call__(self, request: Request) -> BoundLogger:
        """Return a logger bound with request information.

        Returns
        -------
        structlog.stdlib.BoundLogger
            The bound logger.
        """
        if not self.logger:
            self.logger = structlog.get_logger(_logger_name)
            if not self.logger:
                msg = f"Unable to get logger for {_logger_name}"
                raise RuntimeError(msg)

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

        return self.logger.new(
            httpRequest=request_data,
            request_id=str(uuid.uuid4()),
        )


logger_dependency = LoggerDependency()
"""The dependency that will return the logger for the current request."""
