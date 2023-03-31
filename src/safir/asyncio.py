"""Utility functions for asyncio code."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar

T = TypeVar("T")

__all__ = ["run_with_asyncio"]


def run_with_asyncio(
    f: Callable[..., Coroutine[Any, Any, T]]
) -> Callable[..., T]:
    """Run the decorated function with `asyncio.run`.

    Intended to be used as a decorator around an async function that needs to
    be run in a sync context.  The decorated function will be run with
    `asyncio.run` when invoked.  The caller must not already be inside an
    asyncio task.

    Parameters
    ----------
    f
        The function to wrap.

    Examples
    --------
    An application that uses Safir and `Click`_ may use the following Click
    command function to initialize a database.

    .. code-block:: python

       import structlog
       from safir.asyncio import run_with_asyncio
       from safir.database import initialize_database

       from .config import config
       from .schema import Base


       @main.command()
       @run_with_asyncio
       async def init() -> None:
           logger = structlog.get_logger(config.safir.logger_name)
           engine = await initialize_database(
               config.database_url,
               config.database_password,
               logger,
               schema=Base.metadata,
           )
           await engine.dispose()
    """

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return asyncio.run(f(*args, **kwargs))

    return wrapper
