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
from pydantic import BaseModel
from structlog.stdlib import BoundLogger

from . import ArqMode, ArqQueue, MockArqQueue, RedisArqQueue, WorkerSettings

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

    arq_mode: ArqMode
    """What mode to use for the arq queue."""

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

    result_id: str
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
        self._cause_type: str | None = None
        self._traceback: str | None = None
        self._add_traceback = add_traceback

    def __reduce__(self) -> str | tuple:
        # Ensure the cause information is serialized before pickling.
        self._cause_type = self._serialize_cause_type()
        self._traceback = self._serialize_traceback()
        return super().__reduce__()

    @property
    def cause_type(self) -> str | None:
        """Type of the exception that triggered this error, if known."""
        if not self._cause_type:
            self._cause_type = self._serialize_cause_type()
        return self._cause_type

    @property
    def traceback(self) -> str | None:
        """Traceback of the underlying exception, if desired."""
        if not self._traceback:
            self._traceback = self._serialize_traceback()
        return self._traceback

    def _serialize_cause_type(self) -> str | None:
        """Serialize the type of exception from ``__cause__``."""
        if not self.__cause__:
            return None
        return type(self.__cause__).__qualname__

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


def build_worker[T: BaseModel](
    worker: Callable[[T, WorkerJobInfo, BoundLogger], list[WorkerResult]],
    config: WorkerConfig[T],
    logger: BoundLogger,
) -> WorkerSettings:
    """Construct an arq worker for the provided backend function.

    Builds an arq worker configuration that wraps the provided sync function
    and executes it on messages to the default arq queue. Messages to the UWS
    queue will be sent on job start and after job completion so that the UWS
    database can be updated.

    Unfortunately, the built-in arq ``on_job_start`` and ``after_job_end``
    hooks can't be used because they don't receive any arguments to the job
    and we need to tell the UWS handlers the job ID to act on. This means that
    we'll send the UWS queue message before the results are recorded in Redis,
    so the UWS handler has to deal with that.

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
        nonlocal logger
        logger = logger.bind(worker_instance=uuid.uuid4().hex)

        # The queue to which to send UWS notification messages.
        if config.arq_mode == ArqMode.production:
            settings = config.arq_redis_settings
            arq: ArqQueue = await RedisArqQueue.initialize(
                settings, default_queue_name=UWS_QUEUE_NAME
            )
        else:
            arq = MockArqQueue(default_queue_name=UWS_QUEUE_NAME)

        ctx["arq"] = arq
        ctx["logger"] = logger
        ctx["pool"] = ProcessPoolExecutor(1)

        logger.info("Worker startup complete")

    async def shutdown(ctx: dict[Any, Any]) -> None:
        logger: BoundLogger = ctx["logger"]
        pool: ProcessPoolExecutor = ctx["pool"]

        pool.shutdown(wait=True, cancel_futures=True)

        logger.info("Worker shutdown complete")

    async def run(
        ctx: dict[Any, Any], params_raw: dict[str, Any], info: WorkerJobInfo
    ) -> list[WorkerResult]:
        arq: ArqQueue = ctx["arq"]
        logger: BoundLogger = ctx["logger"]
        pool: ProcessPoolExecutor = ctx["pool"]

        params = config.parameters_class.model_validate(params_raw)
        logger = logger.bind(
            task=worker.__qualname__,
            job_id=info.job_id,
            user=info.user,
            params=params.model_dump(mode="json"),
        )
        if info.run_id:
            logger = logger.bind(run_id=info.run_id)

        start = datetime.now(tz=UTC)
        await arq.enqueue("uws_job_started", info.token, info.job_id, start)
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
        finally:
            await arq.enqueue("uws_job_completed", info.token, info.job_id)

    # Since the worker is running sync jobs, run one job per pod since they
    # will be serialized anyway and no parallelism is possible. This also
    # allows us to easily restart the job pool on timeout or job abort. If
    # async worker support is added, consider making this configurable.
    return WorkerSettings(
        functions=[func(run, name=worker.__qualname__)],
        redis_settings=config.arq_redis_settings,
        job_completion_wait=config.grace_period,
        job_timeout=config.timeout,
        max_jobs=1,
        allow_abort_jobs=True,
        on_startup=startup,
        on_shutdown=shutdown,
    )
