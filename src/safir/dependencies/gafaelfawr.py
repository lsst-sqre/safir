"""Gafaelfawr authentication dependencies."""

from typing import Annotated

from fastapi import Depends, Header
from structlog.stdlib import BoundLogger

from .logger import logger_dependency

__all__ = [
    "auth_delegated_token_dependency",
    "auth_dependency",
    "auth_logger_dependency",
]


async def auth_dependency(
    x_auth_request_user: Annotated[str, Header(include_in_schema=False)],
) -> str:
    """Retrieve authentication information from HTTP headers.

    Intended for use with applications protected by Gafaelfawr, this retrieves
    authentication information from headers added to the incoming request by
    the Gafaelfawr ``auth_request`` NGINX subhandler.
    """
    return x_auth_request_user


async def auth_delegated_token_dependency(
    x_auth_request_token: Annotated[str, Header(include_in_schema=False)],
) -> str:
    """Retrieve Gafaelfawr delegated token from HTTP headers.

    Intended for use with applications protected by Gafaelfawr, this retrieves
    a delegated token from headers added to the incoming request by the
    Gafaelfawr ``auth_request`` NGINX subhandler. The delegated token can be
    used to make requests to other services on the user's behalf. See `the
    Gafaelfawr documentation
    <https://gafaelfawr.lsst.io/user-guide/gafaelfawringress.html#requesting-delegated-tokens>`__
    for more details.
    """
    return x_auth_request_token


async def auth_logger_dependency(
    user: Annotated[str, Depends(auth_dependency)],
    logger: Annotated[BoundLogger, Depends(logger_dependency)],
) -> BoundLogger:
    """Logger bound to the authenticated user."""
    return logger.bind(user=user)
