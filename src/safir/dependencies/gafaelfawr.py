"""Gafaelfawr authentication dependencies."""

from fastapi import Depends, Header
from structlog.stdlib import BoundLogger

from .logger import logger_dependency

__all__ = [
    "auth_dependency",
    "auth_logger_dependency",
]


async def auth_dependency(
    x_auth_request_user: str = Header(..., include_in_schema=False)
) -> str:
    """Retrieve authentication information from HTTP headers.

    Intended for use with applications protected by Gafaelfawr, this retrieves
    authentication information from headers added to the incoming request by
    the Gafaelfawr ``auth_request`` NGINX subhandler.
    """
    return x_auth_request_user


async def auth_logger_dependency(
    user: str = Depends(auth_dependency),
    logger: BoundLogger = Depends(logger_dependency),
) -> BoundLogger:
    """Logger bound to the authenticated user."""
    return logger.bind(user=user)
