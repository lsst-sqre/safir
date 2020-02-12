"""Utilities for using the aiohttp client in Safir-based apps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from aiohttp import ClientSession

__all__ = ["init_http_session"]


if TYPE_CHECKING:
    from aiohttp.web import Application


async def init_http_session(app: Application) -> AsyncGenerator:
    """Create an aiohttp.ClientSession and make it available as a
    ``"safir/httpSession"`` key on the application.

    Parameters
    ----------
    app : `aiohttp.web.Application`
        The aiohttp.web-based application.

    Notes
    -----
    Use this function as a `cleanup context
    <https://aiohttp.readthedocs.io/en/stable/web_reference.html#aiohttp.web.Application.cleanup_ctx>`__:

    .. code-block:: python

       app.cleanup_ctx.append(init_http_session)

    The session is automatically closed on shut down.

    To access the session:

    .. code-block:: python

       session = app["safir/httpSession"]
    """
    key = "safir/httpSession"

    # Startup phase
    session = ClientSession()
    app[key] = session
    yield

    # Cleanup phase
    await app[key].close()
