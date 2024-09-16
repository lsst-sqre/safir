"""Define arq workers for an application using UWS."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ParamSpec

from sqlalchemy.ext.asyncio import async_scoped_session
from structlog.stdlib import BoundLogger

from safir.arq import (
    ArqMode,
    ArqQueue,
    JobNotFound,
    JobResult,
    JobResultUnavailable,
    MockArqQueue,
    RedisArqQueue,
)
from safir.arq.uws import WorkerError, WorkerTransientError
from safir.database import (
    create_async_session,
    create_database_engine,
    is_database_current,
)
from safir.datetime import format_datetime_for_logging
from safir.dependencies.http_client import http_client_dependency
from safir.slack.blockkit import SlackException
from safir.slack.webhook import SlackIgnoredException, SlackWebhookClient

from ._config import UWSConfig
from ._constants import JOB_RESULT_TIMEOUT
from ._exceptions import DatabaseSchemaError, TaskError, UnknownJobError
from ._models import UWSJob
from ._service import JobService
from ._storage import JobStore

P = ParamSpec("P")

__all__ = [
    "close_uws_worker_context",
    "create_uws_worker_context",
    "uws_expire_jobs",
    "uws_job_completed",
    "uws_job_started",
]


async def create_uws_worker_context(
    config: UWSConfig,
    logger: BoundLogger,
    *,
    check_schema: bool = False,
    alembic_config_path: Path = Path("alembic.ini"),
) -> dict[str, Any]:
    """Construct the arq context for UWS workers.

    The return value is a dictionary that should be merged with the ``ctx``
    dictionary that is passed to each worker.

    Parameters
    ----------
    config
        UWS configuration.
    logger
        Logger for the worker to use.
    check_schema
        Whether to check the database schema version with Alembic on startup.
    alembic_config_path
        When checking the schema, use this path to the Alembic
        configuration.

    Returns
    -------
    dict
        Keys to add to the ``ctx`` dictionary.

    Raises
    ------
    DatabaseSchemaError
        Raised if the UWS database schema is out of date.
    """
    logger = logger.bind(worker_instance=uuid.uuid4().hex)

    # The queue from which to retrieve results is the main work queue,
    # which uses the default arq queue name. Note that this is not the
    # separate UWS queue this worker is running against.
    if config.arq_mode == ArqMode.production:
        settings = config.arq_redis_settings
        arq: ArqQueue = await RedisArqQueue.initialize(settings)
    else:
        arq = MockArqQueue()

    engine = create_database_engine(
        config.database_url,
        config.database_password,
        isolation_level="REPEATABLE READ",
    )
    if check_schema:
        if not await is_database_current(engine, logger, alembic_config_path):
            raise DatabaseSchemaError("UWS database schema out of date")
    session = await create_async_session(engine, logger)
    storage = JobStore(session)
    service = JobService(
        config=config, arq_queue=arq, storage=storage, logger=logger
    )
    slack = None
    if config.slack_webhook:
        slack = SlackWebhookClient(
            config.slack_webhook.get_secret_value(),
            "vo-cutouts-db-worker",
            logger,
        )

    logger.info("Worker startup complete")
    return {
        "arq": arq,
        "logger": logger,
        "service": service,
        "session": session,
        "slack": slack,
        "storage": storage,
    }


async def close_uws_worker_context(ctx: dict[Any, Any]) -> None:
    """Close the context used by the UWS workers.

    Performs any necessary cleanup of persistent objects stored in the ``ctx``
    argument passed to each worker.

    Parameters
    ----------
    ctx
        Worker context.
    """
    logger: BoundLogger = ctx["logger"]
    session: async_scoped_session = ctx["session"]

    await session.remove()

    # Possibly initialized by the Slack webhook client.
    await http_client_dependency.aclose()

    logger.info("Worker shutdown complete")


async def uws_expire_jobs(ctx: dict[Any, Any]) -> None:
    """Delete jobs that have passed their destruction time.

    Parameters
    ----------
    ctx
        arq context.
    """
    slack: SlackWebhookClient | None = ctx["slack"]
    service: JobService = ctx["service"]

    try:
        await service.delete_expired()
    except Exception as e:
        if slack:
            await slack.post_uncaught_exception(e)
        raise


async def uws_job_started(
    ctx: dict[Any, Any], job_id: str, start_time: datetime
) -> None:
    """Mark a UWS job as executing.

    Parameters
    ----------
    ctx
        arq context.
    job_id
        UWS job identifier.
    start_time
        When the job was started.
    """
    logger: BoundLogger = ctx["logger"].bind(task="job_started", job_id=job_id)
    slack: SlackWebhookClient | None = ctx["slack"]
    storage: JobStore = ctx["storage"]

    try:
        await storage.mark_executing(job_id, start_time)
        logger.info(
            "Marked job as started",
            start_time=format_datetime_for_logging(start_time),
        )
    except UnknownJobError:
        logger.warning("Job not found to mark as started", job_id=job_id)
    except Exception as e:
        if slack:
            await slack.post_uncaught_exception(e)
        raise


async def _annotate_worker_error(
    exc: Exception, job: UWSJob, slack: SlackWebhookClient | None = None
) -> Exception:
    """Convert and possibly report a backend worker error.

    Convert the backend worker error to a task error and annotate it with task
    information. Report the error to Slack if Slack is configured and the
    error is not ignored for Slack reporting purposes.

    Parameters
    ----------
    exc
        Worker exception.
    job
        Associated UWS job.
    slack
        Class for reporting errors to Slack, if Slack error reporting is
        enabled.

    Returns
    -------
    TaskError
        Exception converted to a `~safir.uws._exceptions.TaskError`.
    """
    match exc:
        case WorkerError():
            error = TaskError.from_worker_error(exc)
            error.job_id = job.job_id
            error.started_at = job.creation_time
            error.user = job.owner
            if slack and not error.slack_ignore:
                await slack.post_exception(error)
            return error
        case SlackIgnoredException():
            return exc
        case SlackException():
            exc.user = job.owner
            if slack:
                await slack.post_exception(exc)
            return exc
        case _:
            if slack:
                await slack.post_uncaught_exception(exc)
            return exc


async def _get_job_result(arq: ArqQueue, arq_job_id: str) -> JobResult:
    """Get the result of the job, which may require waiting for it."""
    now = datetime.now(tz=UTC)
    end = now + JOB_RESULT_TIMEOUT
    while now < end:
        await asyncio.sleep(0.5)
        with contextlib.suppress(JobResultUnavailable):
            return await arq.get_job_result(arq_job_id)

    # If we fell off the end of the retry loop, try one more time.
    return await arq.get_job_result(arq_job_id)


async def uws_job_completed(ctx: dict[Any, Any], job_id: str) -> None:
    """Mark a UWS job as completed.

    Recover the exception if the job failed and record that as the job error.
    Because we can't use the arq ``after_job_end`` callback, the job results
    may not be available yet when we're called, which requires polling.

    Parameters
    ----------
    ctx
        arq context.
    job_id
        UWS job identifier.
    """
    arq: ArqQueue = ctx["arq"]
    logger: BoundLogger = ctx["logger"].bind(
        task="job_completed", job_id=job_id
    )
    slack: SlackWebhookClient | None = ctx["slack"]
    storage: JobStore = ctx["storage"]

    try:
        job = await storage.get(job_id)
        arq_job_id = job.message_id
        if not arq_job_id:
            msg = "Job has no associated arq job ID, cannot mark completed"
            logger.error(msg)
            return
        logger = logger.bind(arq_job_id=arq_job_id)

        # Get the job results.
        try:
            result = await _get_job_result(arq, arq_job_id)
        except (JobNotFound, JobResultUnavailable) as e:
            logger.exception("Cannot retrieve job result")
            exc = WorkerTransientError(
                "Cannot retrieve job result from job queue",
                f"{type(e).__name__}: {e!s}",
                add_traceback=True,
            )
            exc.__cause__ = e
            error = await _annotate_worker_error(exc, job, slack)
            await storage.mark_failed(job_id, error)
            return

        # If the job failed and Slack reporting is enabled, annotate the job
        # with some more details and report it to Slack.
        if isinstance(result.result, Exception):
            error = await _annotate_worker_error(result.result, job, slack)
            result.result = error

        # Mark the job as completed.
        await storage.mark_completed(job_id, result)
        logger.info("Marked job as completed")
    except UnknownJobError:
        logger.warning("Job not found to mark as completed")
    except Exception as e:
        if slack:
            await slack.post_uncaught_exception(e)
        raise
