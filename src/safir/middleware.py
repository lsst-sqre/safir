"""Middleware for aiohttp.web servers."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from aiohttp import web

from safir.logging import response_logger

__all__ = ["bind_logger"]


if TYPE_CHECKING:
    from typing import Awaitable, Callable

    from aiohttp.web.web_response import Request, StreamResponse

    Handler = Callable[[Request], Awaitable[StreamResponse]]
    Middleware = Callable[[Request, Handler], Awaitable[StreamResponse]]


@web.middleware
async def bind_logger(request: Request, handler: Handler) -> StreamResponse:
    """Bind request metadata to the context-local structlog logger.

    This is an aiohttp.web middleware.

    Parameters
    ----------
    request
        The aiohttp.web request.
    handler
        The application's request handler.

    Returns
    -------
    response
        The response with the ``logger`` key attached to it. This
        structlog-based logger is bound with context about the request. See
        Notes for details.

    Notes
    -----
    This middleware initializes a new response-local structlog logger with
    context bound to it. All logging calls within the context of a response
    include this context. This makes it easy to search, filter, and aggregate
    logs for a specififc request. For background, see
    http://www.structlog.org/en/stable/getting-started.html#building-a-context

    The context fields are:

    ``request_id``
       A random UUID4 string that uniquely identifies the request.

    ``path``
       The path of the request.

    ``method``
       The http method of the request.

    **Logger name**

    By default, the logger is named for the ``logger_name`` attribute of the
    configuration object (``app["safir/config"]``). If that configuration is
    not set, the logger name falls back to ``__name__``.

    Examples
    --------
    **Setting up the middleware**

    Use the `safir.middleware.setup_middleware` function to set this up:

    .. code-block:: python

       app = web.Application()
       app["safir/config"] = Configuration()
       app.middlewares.append(bind_logger)

    Remember that ``bind_logger`` names the logger according to the
    ``logger_name`` attribute of the configuration, ``app["safir/config"]``.

    **Using the logger**

    Within a handler, you can access the logger directly from the
    ``safir/logger`` key of the request object:

    .. code-block:: python

       @routes.get("/")
       async def get_index(request):
           logger = request["safir/logger"]
           logger.info("Logged message", somekey="somevalue")

    If the request object is not available, you can still get the logger
    through the `safir.logging.get_response_logger` function:

    .. code-block:: python

       from safir.logging import get_response_logger

       logger = get_response_logger()
       logger.info("My message", somekey="somevalue")

    Under the hood, you can also get this logger from the
    `safir.logging.response_logger` context variable. For example:

    .. code-block:: python

       from safir.logging import response_logger

       logger = response_logger.get()
       logger.info("My message", somekey="somevalue")

    The ``response_logger.get()`` syntax is because ``response_logger`` is a
    `contextvars.ContextVar`. A `~contextvars.ContextVar` is isolated to each
    asyncio Task, which makes it great for storing context specific to each
    reponse.

    The ``request["safir/logger"]`` and `safir.logging.get_response_logger`
    APIs are the best ways to get the logger.
    """
    try:
        config = request.config_dict["safir/config"]
        logger_name = config.logger_name
    except (KeyError, AttributeError):
        logger_name = __name__

    logger = structlog.get_logger(logger_name)
    logger = logger.new(
        request_id=str(uuid.uuid4()),
        path=request.path,
        method=request.method,
    )

    # Add the logger to the ContextVar
    response_logger.set(logger)

    # Also add the logger to the request instance
    request["safir/logger"] = logger

    response = await handler(request)

    return response
