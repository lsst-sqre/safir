"""A FastAPI dependency that supplies a Redis connection for arq_."""

from __future__ import annotations

from arq.connections import RedisSettings

from ..arq import ArqMode, ArqQueue, MockArqQueue, RedisArqQueue

__all__ = ["ArqDependency", "arq_dependency"]


class ArqDependency:
    """FastAPI dependency providing a client for enqueuing tasks.

    This class maintains a singleton Redis client for enqueuing tasks to an
    arq_ worker pool and provides it to handler methods via the FastAPI
    dependency interface.
    """

    def __init__(self) -> None:
        self._arq_queue: ArqQueue | None = None

    async def initialize(
        self, *, mode: ArqMode, redis_settings: RedisSettings | None
    ) -> None:
        """Initialize the dependency (call during the FastAPI start-up event).

        Parameters
        ----------
        mode
            The mode to operate the queue dependency in. With
            `safir.arq.ArqMode.production`, this method initializes a
            Redis-based arq queue and the dependency creates a
            `safir.arq.RedisArqQueue` client.

            With `safir.arq.ArqMode.test`, this method instead initializes an
            in-memory mocked version of arq that you use with the
            `safir.arq.MockArqQueue` client.
        redis_settings
            The arq Redis settings, required when the ``mode`` is
            `safir.arq.ArqMode.production`. See arq's
            `~arq.connections.RedisSettings` documentation for details on
            this object.

        Examples
        --------
        .. code-block:: python

           from fastapi import Depends, FastAPI
           from safir.arq import ArqMode, ArqQueue
           from safir.dependencies.arq import arq_dependency

           app = FastAPI()


           @app.on_event("startup")
           async def startup() -> None:
               await arq_dependency.initialize(mode=ArqMode.test)


           @app.post("/")
           async def post_job(
               arq_queue: ArqQueue = Depends(arq_dependency),
           ) -> Dict[str, Any]:
               job = await arq_queue.enqueue("test_task", "hello", an_int=42)
               return {"job_id": job.id}
        """
        if mode == ArqMode.production:
            if not redis_settings:
                raise RuntimeError(
                    "The redis_settings argument must be set for arq in "
                    "production."
                )
            self._arq_queue = await RedisArqQueue.initialize(redis_settings)
        else:
            self._arq_queue = MockArqQueue()

    async def __call__(self) -> ArqQueue:
        """Get the arq queue.

        This method is called for your by ``fastapi.Depends``.
        """
        if self._arq_queue is None:
            raise RuntimeError("ArqDependency is not initialized")
        return self._arq_queue


arq_dependency = ArqDependency()
"""Singleton instance of `ArqDependency` as a FastAPI dependency."""
