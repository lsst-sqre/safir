"""Tests for arq worker construction."""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import Any
from unittest.mock import ANY

import pytest
from arq.constants import default_queue_name
from arq.jobs import JobStatus
from arq.worker import Function
from structlog.stdlib import BoundLogger
from vo_models.uws.types import ErrorType, ExecutionPhase

from safir.arq import JobMetadata, MockArqQueue
from safir.arq.uws import (
    UWS_QUEUE_NAME,
    WorkerConfig,
    WorkerFatalError,
    WorkerJobInfo,
    WorkerResult,
    WorkerTimeoutError,
    build_worker,
)
from safir.datetime import current_datetime
from safir.testing.slack import MockSlackWebhook
from safir.uws import JobResult, UWSApplication, UWSConfig
from safir.uws._constants import UWS_DATABASE_TIMEOUT
from safir.uws._dependencies import UWSFactory
from safir.uws._storage import JobStore

from ..support.uws import SimpleParameters


def hello(
    params: SimpleParameters, info: WorkerJobInfo, logger: BoundLogger
) -> list[WorkerResult]:
    if params.name == "Timeout":
        time.sleep(120)
    return [
        WorkerResult(
            result_id="greeting", url=f"https://example.com/{params.name}"
        )
    ]


@pytest.mark.asyncio
async def test_build_worker(
    uws_config: UWSConfig,
    test_token: str,
    test_username: str,
    logger: BoundLogger,
) -> None:
    redis_settings = uws_config.arq_redis_settings
    worker_config = WorkerConfig(
        arq_mode=uws_config.arq_mode,
        arq_queue_url=(
            f"redis://{redis_settings.host}:{redis_settings.port}"
            f"/{redis_settings.database}"
        ),
        arq_queue_password=redis_settings.password,
        grace_period=timedelta(seconds=60),
        parameters_class=SimpleParameters,
        timeout=uws_config.execution_duration,
    )
    settings = build_worker(hello, worker_config, logger)
    assert not settings.cron_jobs
    assert len(settings.functions) == 1
    assert isinstance(settings.functions[0], Function)
    assert settings.functions[0].name == hello.__qualname__
    assert settings.redis_settings == uws_config.arq_redis_settings
    assert settings.allow_abort_jobs
    assert settings.job_completion_wait == timedelta(seconds=60)
    assert settings.queue_name == default_queue_name
    assert settings.on_startup
    assert settings.on_shutdown

    # Run the startup hook.
    ctx: dict[Any, Any] = {}
    startup = settings.on_startup
    await startup(ctx)
    assert isinstance(ctx["arq"], MockArqQueue)
    assert isinstance(ctx["logger"], BoundLogger)
    arq = ctx["arq"]
    assert arq.default_queue_name == UWS_QUEUE_NAME

    # Run the worker.
    function = settings.functions[0].coroutine
    params = SimpleParameters(name="Roger")
    info = WorkerJobInfo(
        job_id="42",
        user=test_username,
        token=test_token,
        timeout=timedelta(minutes=1),
        run_id="some-run-id",
    )
    result = await function(ctx, params, info)
    assert result == [
        WorkerResult(result_id="greeting", url="https://example.com/Roger")
    ]
    assert list(arq._job_metadata[UWS_QUEUE_NAME].values()) == [
        JobMetadata(
            id=ANY,
            name="uws_job_started",
            args=(test_token, "42", ANY),
            kwargs={},
            enqueue_time=ANY,
            status=JobStatus.queued,
            queue_name=UWS_QUEUE_NAME,
        ),
        JobMetadata(
            id=ANY,
            name="uws_job_completed",
            args=(test_token, "42"),
            kwargs={},
            enqueue_time=ANY,
            status=JobStatus.queued,
            queue_name=UWS_QUEUE_NAME,
        ),
    ]

    # Run the shutdown hook.
    shutdown = settings.on_shutdown
    await shutdown(ctx)


@pytest.mark.asyncio
async def test_timeout(
    uws_config: UWSConfig,
    test_token: str,
    test_username: str,
    logger: BoundLogger,
) -> None:
    redis_settings = uws_config.arq_redis_settings
    worker_config = WorkerConfig(
        arq_mode=uws_config.arq_mode,
        arq_queue_url=(
            f"redis://{redis_settings.host}:{redis_settings.port}"
            f"/{redis_settings.database}"
        ),
        arq_queue_password=redis_settings.password,
        grace_period=timedelta(seconds=60),
        parameters_class=SimpleParameters,
        timeout=uws_config.execution_duration,
    )
    settings = build_worker(hello, worker_config, logger)
    assert isinstance(settings.functions[0], Function)

    # Run the startup hook.
    ctx: dict[Any, Any] = {}
    startup = settings.on_startup
    assert startup
    await startup(ctx)
    arq = ctx["arq"]

    # Run the worker.
    function = settings.functions[0].coroutine
    params = SimpleParameters(name="Timeout")
    info = WorkerJobInfo(
        job_id="42",
        user=test_username,
        token=test_token,
        timeout=timedelta(seconds=1),
        run_id="some-run-id",
    )
    with pytest.raises(WorkerTimeoutError):
        await function(ctx, params, info)
    assert list(arq._job_metadata[UWS_QUEUE_NAME].values()) == [
        JobMetadata(
            id=ANY,
            name="uws_job_started",
            args=(test_token, "42", ANY),
            kwargs={},
            enqueue_time=ANY,
            status=JobStatus.queued,
            queue_name=UWS_QUEUE_NAME,
        ),
        JobMetadata(
            id=ANY,
            name="uws_job_completed",
            args=(test_token, "42"),
            kwargs={},
            enqueue_time=ANY,
            status=JobStatus.queued,
            queue_name=UWS_QUEUE_NAME,
        ),
    ]

    # Make sure that handling the timeout didn't break the worker and we can
    # run another job successfully.
    params = SimpleParameters(name="Roger")
    info.job_id = "43"
    result = await function(ctx, params, info)
    assert result == [
        WorkerResult(result_id="greeting", url="https://example.com/Roger")
    ]

    # Run the shutdown hook.
    shutdown = settings.on_shutdown
    assert shutdown
    await shutdown(ctx)


@pytest.mark.asyncio
async def test_build_uws_worker(
    arq_queue: MockArqQueue,
    uws_config: UWSConfig,
    test_token: str,
    test_username: str,
    uws_factory: UWSFactory,
    mock_slack: MockSlackWebhook,
    logger: BoundLogger,
) -> None:
    uws = UWSApplication(uws_config)
    job_service = uws_factory.create_job_service()
    job = await job_service.create(test_token, SimpleParameters(name="Ahmed"))
    results = [WorkerResult(result_id="greeting", url="https://example.com")]
    await job_service.start(test_token, test_username, job.id)
    job = await job_service.get(test_token, job.id)
    assert job.start_time is None
    assert job.phase == ExecutionPhase.QUEUED

    # Construct the arq configuration and check it.
    settings = uws.build_worker(logger)
    assert len(settings.functions) == 2
    job_started = settings.functions[0]
    assert callable(job_started)
    job_completed = settings.functions[1]
    assert callable(job_completed)
    assert settings.redis_settings == uws_config.arq_redis_settings
    assert not settings.allow_abort_jobs
    assert settings.job_completion_wait == UWS_DATABASE_TIMEOUT
    assert settings.queue_name == UWS_QUEUE_NAME
    assert settings.on_startup
    assert settings.on_shutdown

    # Run the startup hook.
    ctx: dict[Any, Any] = {}
    startup = settings.on_startup
    await startup(ctx)
    assert isinstance(ctx["arq"], MockArqQueue)
    assert isinstance(ctx["logger"], BoundLogger)
    assert isinstance(ctx["storage"], JobStore)
    assert ctx["arq"].default_queue_name == default_queue_name
    ctx["arq"] = arq_queue

    # Test starting a job.
    now = current_datetime()
    assert job.message_id
    await arq_queue.set_in_progress(job.message_id)
    await job_started(ctx, test_token, job.id, now)
    job = await job_service.get(test_token, job.id)
    assert job.phase == ExecutionPhase.EXECUTING
    assert job.start_time == now

    # Test finishing a job.
    assert job.message_id
    await asyncio.gather(
        job_completed(ctx, test_token, job.id),
        arq_queue.set_complete(job.message_id, result=results),
    )
    job = await job_service.get(test_token, job.id)
    assert job.phase == ExecutionPhase.COMPLETED
    assert job.end_time
    assert job.end_time.microsecond == 0
    assert now <= job.end_time <= current_datetime()
    assert job.results == [JobResult.from_worker_result(r) for r in results]
    assert mock_slack.messages == []

    def nonnegative(value: int) -> None:
        if value < 0:
            raise ValueError("Value not nonnegative")

    def make_exception() -> None:
        try:
            nonnegative(-1)
        except Exception as e:
            raise WorkerFatalError(
                "Something", "went wrong", add_traceback=True
            ) from e

    # Test starting and erroring a job with a TaskError.
    job = await job_service.create(test_token, SimpleParameters(name="Ahmed"))
    await job_service.start(test_token, test_username, job.id)
    job = await job_service.get(test_token, job.id)
    assert job.message_id
    await arq_queue.set_in_progress(job.message_id)
    await job_started(ctx, test_token, job.id, now)
    try:
        make_exception()
    except WorkerFatalError as e:
        error = e
    await asyncio.gather(
        job_completed(ctx, test_token, job.id),
        arq_queue.set_complete(job.message_id, result=error, success=False),
    )
    job = await job_service.get(test_token, job.id)
    assert job.phase == ExecutionPhase.ERROR
    assert job.end_time
    assert job.end_time.microsecond == 0
    assert now <= job.end_time <= current_datetime()
    assert job.errors
    assert len(job.errors) == 1
    assert job.errors[0].type == ErrorType.FATAL
    assert job.errors[0].code == "Error"
    assert job.errors[0].message == "Something"
    assert job.errors[0].detail
    assert "went wrong" in job.errors[0].detail
    assert error.traceback
    assert error.traceback in job.errors[0].detail
    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "text": {
                        "text": "Error in vo-cutouts-db-worker: Something",
                        "type": "mrkdwn",
                        "verbatim": True,
                    },
                    "type": "section",
                },
                {
                    "fields": [
                        {
                            "text": "*Exception type*\nTaskError",
                            "type": "mrkdwn",
                            "verbatim": True,
                        },
                        {
                            "text": "*UWS job ID*\n2",
                            "type": "mrkdwn",
                            "verbatim": True,
                        },
                        {"text": ANY, "type": "mrkdwn", "verbatim": True},
                        {"text": ANY, "type": "mrkdwn", "verbatim": True},
                        {
                            "text": f"*User*\n{test_username}",
                            "type": "mrkdwn",
                            "verbatim": True,
                        },
                    ],
                    "type": "section",
                },
                {
                    "text": {
                        "text": "*Original exception*\nValueError",
                        "type": "mrkdwn",
                        "verbatim": True,
                    },
                    "type": "section",
                },
                {
                    "text": {
                        "text": "*Detail*\nwent wrong",
                        "type": "mrkdwn",
                        "verbatim": True,
                    },
                    "type": "section",
                },
            ],
            "attachments": [
                {
                    "blocks": [
                        {
                            "text": {
                                "text": (
                                    f"*Traceback*\n```\n{error.traceback}```"
                                ),
                                "type": "mrkdwn",
                                "verbatim": True,
                            },
                            "type": "section",
                        }
                    ]
                }
            ],
        },
    ]

    # Test starting and erroring a job with an unknown exception.
    mock_slack.messages = []
    job = await job_service.create(test_token, SimpleParameters(name="Ahmed"))
    await job_service.start(test_token, test_username, job.id)
    job = await job_service.get(test_token, job.id)
    assert job.message_id
    await arq_queue.set_in_progress(job.message_id)
    await job_started(ctx, test_token, job.id, now)
    exc = ValueError("some error")
    await asyncio.gather(
        job_completed(ctx, test_token, job.id),
        arq_queue.set_complete(job.message_id, result=exc, success=False),
    )
    job = await job_service.get(test_token, job.id)
    assert job.phase == ExecutionPhase.ERROR
    assert job.errors
    assert len(job.errors) == 1
    assert job.errors[0].type == ErrorType.FATAL
    assert job.errors[0].code == "Error"
    assert job.errors[0].message == "Unknown error executing task"
    assert job.errors[0].detail == "ValueError: some error"
    assert mock_slack.messages == [
        {
            "blocks": [
                {
                    "text": {
                        "text": "Uncaught exception in vo-cutouts-db-worker",
                        "type": "mrkdwn",
                        "verbatim": True,
                    },
                    "type": "section",
                },
                {
                    "fields": [
                        {
                            "text": "*Exception type*\nValueError",
                            "type": "mrkdwn",
                            "verbatim": True,
                        },
                        {"text": ANY, "type": "mrkdwn", "verbatim": True},
                    ],
                    "type": "section",
                },
                {
                    "text": {
                        "text": (
                            "*Exception*\n```\nValueError: some error\n```"
                        ),
                        "type": "mrkdwn",
                        "verbatim": True,
                    },
                    "type": "section",
                },
                {"type": "divider"},
            ],
        },
    ]
