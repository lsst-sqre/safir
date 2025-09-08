"""Database transaction retry support."""

import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import overload

from sqlalchemy.exc import DBAPIError

__all__ = ["retry_async_transaction"]


@overload
def retry_async_transaction[**P, T](
    __func: Callable[P, Coroutine[None, None, T]], /
) -> Callable[P, Coroutine[None, None, T]]: ...


@overload
def retry_async_transaction[**P, T](
    *, delay: float = 0.5, max_tries: int = 3
) -> Callable[
    [Callable[P, Coroutine[None, None, T]]],
    Callable[P, Coroutine[None, None, T]],
]: ...


def retry_async_transaction[**P, T](
    __func: Callable[P, Coroutine[None, None, T]] | None = None,
    /,
    *,
    delay: float = 0.5,
    max_tries: int = 3,
) -> (
    Callable[P, Coroutine[None, None, T]]
    | Callable[
        [Callable[P, Coroutine[None, None, T]]],
        Callable[P, Coroutine[None, None, T]],
    ]
):
    """Retry if a transaction failed.

    If the wrapped method fails with an `sqlalchemy.exc.DBAPIError` exception,
    it is retried up to ``max_tries`` times. Any method with this decorator
    must be idempotent, since it may be re-run multiple times.

    One common use for this decorator is when the database engine has been
    configured with the ``REPEATABLE READ`` transaction isolation level and
    multiple writers may be updating the same object at the same time. The
    loser of the transaction race will raise one of the above exceptions, and
    can be retried with this decorator.

    Parameters
    ----------
    delay
        How long, in seconds, to wait between tries.
    max_tries
        Number of times to retry the transaction. Practical experience with
        ``REPEATABLE READ`` isolation suggests a count of at least three.

    Examples
    --------
    This decorator can be used with any idempotent Python function or method
    that makes database calls and should be retried on the above-listed
    exceptions.

    .. code-block:: python

       from safir.database import retry_async_transaction
       from sqlalchemy.ext.asyncio import async_scoped_session


       @retry_async_transaction(max_tries=5)
       def make_some_database_call(session: async_scoped_session) -> None: ...

    If the default value of ``max_tries`` is acceptable, this decorator can
    be used without arguments.

    .. code-block:: python

       from safir.database import retry_async_transaction
       from sqlalchemy.ext.asyncio import async_scoped_session


       @retry_async_transaction
       def make_some_database_call(session: async_scoped_session) -> None: ...
    """

    def decorator(
        f: Callable[P, Coroutine[None, None, T]],
    ) -> Callable[P, Coroutine[None, None, T]]:
        @wraps(f)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for _ in range(1, max_tries):
                with contextlib.suppress(DBAPIError):
                    return await f(*args, **kwargs)
                await asyncio.sleep(delay)
            return await f(*args, **kwargs)

        return wrapper

    if __func is not None:
        return decorator(__func)
    else:
        return decorator
