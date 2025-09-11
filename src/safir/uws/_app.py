"""Representation of a UWS application."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from structlog.stdlib import BoundLogger

try:
    from safir.arq import ArqQueue, WorkerSettings
    from safir.arq.uws import UWS_QUEUE_NAME
except ImportError as e:
    raise ImportError(
        "The safir.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e
from safir.middleware.ivoa import (
    CaseInsensitiveFormMiddleware,
    CaseInsensitiveQueryMiddleware,
)

from ._config import UWSConfig
from ._constants import UWS_DATABASE_TIMEOUT
from ._dependencies import uws_dependency
from ._exceptions import UWSError
from ._handlers import (
    install_async_post_handler,
    install_availability_handler,
    install_sync_get_handler,
    install_sync_post_handler,
    uws_router,
)
from ._workers import (
    close_uws_worker_context,
    create_uws_worker_context,
    uws_job_completed,
    uws_job_started,
)

__all__ = ["UWSApplication"]


async def _uws_error_handler(
    request: Request, exc: UWSError
) -> PlainTextResponse:
    response = f"{exc.error_code}: {exc!s}\n"
    if exc.detail:
        response += "\n{exc.detail}"
    return PlainTextResponse(response, status_code=exc.status_code)


async def _usage_handler(
    request: Request, exc: RequestValidationError
) -> PlainTextResponse:
    return PlainTextResponse(f"UsageError\n\n{exc!s}", status_code=422)


class UWSApplication:
    """Glue between a FastAPI application and the UWS implementation.

    An instance of this class should be created during construction of the
    service that will use the UWS layer. It provides methods to build route
    handlers, install error handlers, and build the UWS database
    worker. Construction of the backend worker that does the work of the
    service is handled separately so that it can have minimal dependencies.

    Parameters
    ----------
    config
        UWS configuration.
    """

    def __init__(self, config: UWSConfig) -> None:
        self._config = config

    def build_worker(self, logger: BoundLogger) -> WorkerSettings:
        """Construct an arq worker configuration for the UWS worker.

        All UWS job status and results must be stored in the underlying
        database (via Wobbly), since the API serves job information from
        there. To minimize dependencies for the worker, which may (for
        example) pin its own version of SQLAlchemy that may not be compatible
        with that used by the application, the actual worker is not
        responsible for storing the results in the database. Instead, it
        returns results via arq, which temporarily puts them in Redis then
        uses ``on_job_start`` and ``after_job_end`` to notify a different
        queue. Those results are recovered and stored in the database (via
        Wobbly) by a separate arq worker.

        This function defines that database worker. It returns a class
        suitable for assigning to a module variable and referencing as the
        argument to the :command:`arq` command-line tool to start the worker.

        Parameters
        ----------
        logger
            Logger to use for messages.
        """

        async def startup(ctx: dict[Any, Any]) -> None:
            ctx.update(await create_uws_worker_context(self._config, logger))

        async def shutdown(ctx: dict[Any, Any]) -> None:
            await close_uws_worker_context(ctx)

        # Running 10 jobs simultaneously is the arq default as of arq 0.26.0
        # and seems reasonable for database workers.
        return WorkerSettings(
            functions=[uws_job_started, uws_job_completed],
            redis_settings=self._config.arq_redis_settings,
            job_completion_wait=UWS_DATABASE_TIMEOUT,
            job_timeout=UWS_DATABASE_TIMEOUT,
            max_jobs=10,
            queue_name=UWS_QUEUE_NAME,
            on_startup=startup,
            on_shutdown=shutdown,
        )

    async def initialize_fastapi(self) -> None:
        """Initialize the UWS subsystem for FastAPI applications.

        This must be called before any UWS routes are accessed, normally from
        the lifespan function of the FastAPI application.
        """
        await uws_dependency.initialize(self._config)

    def install_error_handlers(self, app: FastAPI) -> None:
        """Install error handlers that follow DALI and UWS conventions.

        This method must be called during application setup for any FastAPI
        app using the UWS layer for correct error message handling. This will
        change the error response for all parameter validation errors from
        FastAPI.

        Currently these error handlers return ``text/plain`` errors. VOTable
        errors may be a better choice, but revision 1.0 of the SODA standard
        only allows ``text/plain`` errors for sync routes.
        """
        app.exception_handler(UWSError)(_uws_error_handler)
        app.exception_handler(RequestValidationError)(_usage_handler)

    def install_handlers(self, router: APIRouter) -> None:
        """Install the route handlers for the service.

        This method will always install a POST handler at the root of the
        router that creates an async job, and handlers under ``/jobs`` that
        implement the UWS protocol for managing those jobs. If
        ``sync_post_route`` is set in the `~safir.uws.UWSConfig` that this
        application was configured with, a POST handler for ``/sync`` to
        create a sync job will be added. If ``sync_get_route`` is set, a GET
        handler for ``/sync`` to create a sync job will be added.
        """
        router.include_router(uws_router, prefix="/jobs")
        install_availability_handler(router)
        if route := self._config.sync_get_route:
            install_sync_get_handler(router, route)
        if route := self._config.sync_post_route:
            install_sync_post_handler(router, route)

        # This handler must be installed directly on the provided router. Do
        # not install it on the UWS router before include_router. The process
        # of copying handlers done by include_router loses the dependency
        # information from the async post handler and causes it to not see any
        # of its job parameters.
        #
        # This is probably because the dependency is a dynamic function not
        # known statically, which may confuse the handler copying code in
        # FastAPI. This problem was last verified in FastAPI 0.111.0.
        install_async_post_handler(router, self._config.async_post_route)

    def install_middleware(self, app: FastAPI) -> None:
        """Install FastAPI middleware needed by UWS.

        UWS unfortunately requires that the key portion of query and form
        parameters be case-insensitive, so UWS FastAPI applications need to
        add custom middleware to lowercase parameter keys. This method does
        that.

        Parameters
        ----------
        app
            FastAPI app.
        """
        app.add_middleware(CaseInsensitiveFormMiddleware)
        app.add_middleware(CaseInsensitiveQueryMiddleware)

    def override_arq_queue(self, arq_queue: ArqQueue) -> None:
        """Change the arq used by the FastAPI route handlers.

        This method is probably only useful for the test suite.

        Parameters
        ----------
        arq_queue
            New arq queue.
        """
        uws_dependency.override_arq_queue(arq_queue)

    async def shutdown_fastapi(self) -> None:
        """Shut down the UWS subsystem for FastAPI applications.

        This should be called during application shutdown, normally from the
        lifespan function of the FastAPI application. Currently, this does
        nothing, but it remains as a hook in case some shutdown is required in
        the future.
        """
