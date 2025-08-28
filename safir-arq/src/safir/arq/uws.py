"""Construction of UWS backend workers."""

import asyncio
import os
import signal
import uuid
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from traceback import format_exception
from typing import Any, ClassVar
from urllib.parse import urlsplit

from arq import func
from arq.connections import RedisSettings
from httpx import AsyncClient, AsyncHTTPTransport, HTTPError, Response
from pydantic import BaseModel
from structlog.stdlib import BoundLogger

from . import WorkerSettings

UWS_QUEUE_NAME = "uws:queue"
"""Name of the arq queue for internal UWS messages."""

__all__ = [
    "UWS_QUEUE_NAME",
    "WorkerConfig",
    "WorkerError",
    "WorkerErrorType",
    "WorkerFatalError",
    "WorkerJobInfo",
    "WorkerResult",
    "WorkerTimeoutError",
    "WorkerTransientError",
    "WorkerUsageError",
    "build_worker",
]


@dataclass
class WorkerConfig[T: BaseModel]:
    """Minimal configuration needed for building a UWS backend worker."""

    arq_queue_url: str
    """URL of the Redis arq queue."""

    arq_queue_password: str | None
    """Password of the Redis arq queue."""

    grace_period: timedelta
    """How long to wait for workers to shut down before cancelling them.

    This should be set to somewhat less than the Kubernetes grace period for
    terminating the pod (about five seconds less, for example).
    """

    parameters_class: type[T]
    """Class of the parameters to pass to the backend worker."""

    timeout: timedelta
    """Maximum execution time.

    Jobs that run longer than this length of time will be automatically
    aborted.
    """

    @property
    def arq_redis_settings(self) -> RedisSettings:
        """Redis settings for arq."""
        database = 0
        url = urlsplit(self.arq_queue_url)
        if url.path:
            database = int(url.path.lstrip("/"))
        return RedisSettings(
            host=url.hostname or "localhost",
            port=url.port or 6379,
            database=database,
            password=self.arq_queue_password,
        )


@dataclass
class WorkerJobInfo:
    """Metadata about the job that may be useful to the backend."""

    job_id: str
    """UWS job identifier (not the same as the arq job ID)."""

    job_url: str
    """URL to the Wobbly endpoint used to update job status."""

    user: str
    """Username of the user who submitted the job."""

    token: str
    """Delegated Gafaelfawr token to act on behalf of the user."""

    timeout: timedelta
    """Maximum execution time for the job."""

    run_id: str | None = None
    """User-supplied run ID, if any."""


class WorkerResult(BaseModel):
    """A single result from the job."""

    id: str
    """Identifier for the result."""

    url: str
    """URL for the result, which must point to a GCS bucket."""

    size: int | None = None
    """Size of the result in bytes."""

    mime_type: str | None = None
    """MIME type of the result."""


class WorkerErrorType(Enum):
    """Types of errors that may be reported by a worker."""

    FATAL = "fatal"
    TRANSIENT = "transient"
    USAGE = "usage"


class WorkerError(Exception):
    """An error occurred during background task processing.

    Attributes
    ----------
    detail
        Additional error detail, not including the traceback if any.
    user
        User whose action triggered this exception, for Slack reporting.

    Parameters
    ----------
    message
        Human-readable error message.
    detail
        Additional details about the error.
    add_traceback
        Whether to add a traceback of the underlying cause to the error
        details.
    """

    error_type: ClassVar[WorkerErrorType] = WorkerErrorType.FATAL
    """Type of error this exception represents."""

    def __init__(
        self,
        message: str,
        detail: str | None = None,
        *,
        add_traceback: bool = False,
    ) -> None:
        super().__init__(message)
        self.detail = detail
        self._add_traceback = add_traceback

    def to_job_error(self) -> dict[str, str | None]:
        """Convert to a job error as required by the Wobbly API."""
        match self.error_type:
            case WorkerErrorType.FATAL:
                error_code = "Error"
                error_type = "fatal"
            case WorkerErrorType.TRANSIENT:
                error_code = "ServiceUnavailable"
                error_type = "transient"
            case WorkerErrorType.USAGE:
                error_code = "UsageError"
                error_type = "fatal"
        traceback = self._serialize_traceback()
        if traceback and self.detail:
            detail: str | None = self.detail + "\n\n" + traceback
        else:
            detail = self.detail or traceback
        return {
            "type": error_type,
            "code": error_code,
            "message": str(self),
            "detail": detail,
        }

    def _serialize_traceback(self) -> str | None:
        """Serialize the traceback from ``__cause__``."""
        if not self._add_traceback or not self.__cause__:
            return None
        return "".join(format_exception(self.__cause__))


class WorkerFatalError(WorkerError):
    """Fatal error occurred during worker processing.

    The parameters or other job information was invalid and this job will
    never succeed.
    """


class WorkerTransientError(WorkerError):
    """Transient error occurred during worker processing.

    The job may be retried with the same parameters and may succeed.
    """

    error_type = WorkerErrorType.TRANSIENT


class WorkerTimeoutError(WorkerTransientError):
    """Transient error occurred during worker processing.

    The job may be retried with the same parameters and may succeed.
    """

    def __init__(self, elapsed: timedelta, timeout: timedelta) -> None:
        msg = (
            f"Job timed out after {elapsed.total_seconds()}s"
            f" (timeout: {timeout.total_seconds()}s)"
        )
        super().__init__(msg)


class WorkerUsageError(WorkerError):
    """Parameters sent by the user were invalid.

    The parameters or other job information was invalid and this job will
    never succeed. This is the same as `WorkerFatalError` except that it
    represents a user error and will not be reported to Slack as a service
    problem.
    """

    error_type = WorkerErrorType.USAGE


def _restart_pool(pool: ProcessPoolExecutor) -> ProcessPoolExecutor:
    """Restart the pool after timeout or job cancellation.

    This is a horrible, fragile hack, but it appears to be the only way to
    enforce a timeout currently in Python since there is no way to abort a
    job already in progress. Find the processes underlying the pool, kill
    them, and then shut down and recreate the pool.
    """
    for pid in pool._processes:  # noqa: SLF001
        os.kill(pid, signal.SIGINT)
    pool.shutdown(wait=True)
    return ProcessPoolExecutor(1)


class _WobblyClient:
    """Minimal Wobbly client.

    Provides only the functionality needed by the UWS backend worker to update
    the job to executing and record the results. This version is suitable for
    installing on top of a Rubin Science Pipelines container running an older
    version of Python.

    Parameters
    ----------
    job_url
        URL to the Wobbly job.
    logger
        Logger to use.
    retries
        Number of times to retry Wobbly requests.
    """

    def __init__(self, logger: BoundLogger, *, retries: int = 2) -> None:
        self._logger = logger

        transport = AsyncHTTPTransport(retries=retries)
        self._client = AsyncClient(transport=transport)

    async def aclose(self) -> None:
        """Close any underlying resources.

        The Wobbly client instance may not be used after this method is
        called.
        """
        await self._client.aclose()

    async def mark_completed(
        self,
        info: WorkerJobInfo,
        results: list[WorkerResult],
    ) -> None:
        """Mark a job as completed.

        Parameters
        ----------
        info
            UWS job information.
        results
            Results of the job.

        Raises
        ------
        HTTPError
            Raised if there is some problem updating Wobbly.
        """
        update = {
            "phase": "COMPLETED",
            "results": [r.model_dump(mode="json") for r in results],
        }
        await self._request("PATCH", info, update)

    async def mark_failed(self, info: WorkerJobInfo, exc: Exception) -> None:
        """Mark a job as failed with an error.

        Currently, only one error is supported, even though Wobbly supports
        associating multiple errors with a job.

        Parameters
        ----------
        info
            UWS job information.
        exc
            Exception of failed job.

        Raises
        ------
        HTTPError
            Raised if there is some problem updating Wobbly.
        """
        if isinstance(exc, WorkerError):
            error = exc.to_job_error()
        else:
            error = {
                "type": "fatal",
                "code": "Error",
                "message": "Unknown error executing task",
                "detail": f"{type(exc).__name__}: {exc!s}",
            }
        update = {"phase": "ERROR", "errors": [error]}
        await self._request("PATCH", info, update)

    async def mark_executing(self, info: WorkerJobInfo) -> None:
        """Mark a job as executing.

        If this fails, log an error but do not raise an exception. We will
        hopefully be able to contact Wobbly when the job finishes, and if not,
        the whole job will be retried.

        Parameters
        ----------
        info
            UWS job information.
        """
        update = {
            "phase": "EXECUTING",
            "start_time": datetime.now(tz=UTC).isoformat(),
        }
        try:
            await self._request("PATCH", info, update)
        except HTTPError:
            logger = self._logger.bind(job_id=info.job_id, user=info.user)
            logger.exception("Cannot set status to executing, continuing")

    async def _request(
        self,
        method: str,
        info: WorkerJobInfo,
        update: dict[str, Any],
    ) -> Response:
        """Send an HTTP request to Wobbly.

        Parameters
        ----------
        method
            HTTP method.
        info
            UWS job information.
        update
            Request body.

        Returns
        -------
        Response
            HTTP response object.

        Raises
        ------
        HTTPError
            Raised if there is some problem updating Wobbly.
        """
        r = await self._client.request(
            method,
            info.job_url,
            headers={"Authorization": f"bearer {info.token}"},
            json=update,
        )
        r.raise_for_status()
        return r


def build_worker[T: BaseModel](
    worker: Callable[[T, WorkerJobInfo, BoundLogger], list[WorkerResult]],
    config: WorkerConfig[T],
    logger: BoundLogger,
) -> WorkerSettings:
    """Construct an arq worker for the provided backend function.

    Builds an arq worker configuration that wraps the provided sync function
    and executes it on messages to the default arq queue. Wobbly will be
    updated when the job starts executing and again when the job finishes.

    Parameters
    ----------
    worker
        Synchronous function that does the actual work. This function will be
        run in a thread pool of size one.
    config
        UWS worker configuration.
    logger
        Logger to use for messages.
    """

    async def startup(ctx: dict[Any, Any]) -> None:
        ctx["logger"] = logger.bind(
            worker=worker.__qualname__, worker_instance=uuid.uuid4().hex
        )
        ctx["pool"] = ProcessPoolExecutor(1)
        ctx["wobbly"] = _WobblyClient(ctx["logger"])

        logger.info("Worker startup complete")

    async def shutdown(ctx: dict[Any, Any]) -> None:
        logger: BoundLogger = ctx["logger"]
        pool: ProcessPoolExecutor = ctx["pool"]
        wobbly: _WobblyClient = ctx["wobbly"]

        pool.shutdown(wait=True, cancel_futures=True)
        await wobbly.aclose()

        logger.info("Worker shutdown complete")

    async def run(
        ctx: dict[Any, Any], params_raw: dict[str, Any], info: WorkerJobInfo
    ) -> list[WorkerResult]:
        logger: BoundLogger = ctx["logger"]
        pool: ProcessPoolExecutor = ctx["pool"]

        params = config.parameters_class.model_validate(params_raw)
        logger = logger.bind(
            job_id=info.job_id,
            user=info.user,
            params=params.model_dump(mode="json"),
        )
        if info.run_id:
            logger = logger.bind(run_id=info.run_id)

        start = datetime.now(tz=UTC)
        loop = asyncio.get_running_loop()
        try:
            async with asyncio.timeout(info.timeout.total_seconds()):
                return await loop.run_in_executor(
                    pool, worker, params, info, logger
                )
        except asyncio.CancelledError:
            ctx["pool"] = _restart_pool(pool)
            raise
        except TimeoutError:
            elapsed = datetime.now(tz=UTC) - start
            ctx["pool"] = _restart_pool(pool)
            raise WorkerTimeoutError(elapsed, info.timeout) from None

    async def run_and_record_status(
        ctx: dict[Any, Any], params_raw: dict[str, Any], info: WorkerJobInfo
    ) -> None:
        wobbly: _WobblyClient = ctx["wobbly"]

        await wobbly.mark_executing(info)
        try:
            results = await run(ctx, params_raw, info)
        except Exception as exc:
            await wobbly.mark_failed(info, exc)
        else:
            await wobbly.mark_completed(info, results)

    # Since the worker is running sync jobs, run one job per pod since they
    # will be serialized anyway and no parallelism is possible. This also
    # allows us to easily restart the job pool on timeout or job abort. If
    # async worker support is added, consider making this configurable.
    return WorkerSettings(
        functions=[func(run_and_record_status, name=worker.__qualname__)],
        redis_settings=config.arq_redis_settings,
        job_completion_wait=config.grace_period,
        job_timeout=config.timeout,
        max_jobs=1,
        allow_abort_jobs=True,
        on_startup=startup,
        on_shutdown=shutdown,
    )
