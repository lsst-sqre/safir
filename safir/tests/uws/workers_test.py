"""Tests for arq worker construction."""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import Any
from unittest.mock import ANY

import pytest
from arq.constants import default_queue_name
from arq.worker import Function
from structlog.stdlib import BoundLogger
from vo_models.uws.types import ErrorType, ExecutionPhase

from safir.arq.uws import (
    WorkerConfig,
    WorkerJobInfo,
    WorkerResult,
    build_worker,
)
from safir.uws import JobError, JobResult, UWSConfig
from safir.uws._dependencies import UWSFactory

from ..support.uws import SimpleParameters


def hello(
    params: SimpleParameters, info: WorkerJobInfo, logger: BoundLogger
) -> list[WorkerResult]:
    if params.name == "Delay":
        time.sleep(0.1)
    if params.name == "Timeout":
        time.sleep(120)
    return [
        WorkerResult(id="greeting", url=f"https://example.com/{params.name}")
    ]


@pytest.mark.asyncio
async def test_build_worker(
    uws_config: UWSConfig,
    uws_factory: UWSFactory,
    test_token: str,
    test_username: str,
    logger: BoundLogger,
) -> None:
    job_service = uws_factory.create_job_service()
    redis_settings = uws_config.arq_redis_settings
    worker_config = WorkerConfig(
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
    assert isinstance(ctx["logger"], BoundLogger)

    # Create a job so that there is a Wobbly entry to update.
    await job_service.create(test_token, SimpleParameters(name="Delay"))

    # Run the worker.
    function = settings.functions[0].coroutine
    params = SimpleParameters(name="Delay")
    info = WorkerJobInfo(
        job_id="1",
        job_url=f"{uws_config.wobbly_url}/jobs/1",
        user=test_username,
        token=test_token,
        timeout=timedelta(minutes=1),
    )
    worker_task = asyncio.create_task(function(ctx, params, info))
    await asyncio.sleep(0.05)
    job = await job_service.get(test_token, "1")
    assert job.phase == ExecutionPhase.EXECUTING
    assert await worker_task is None
    job = await job_service.get(test_token, "1")
    assert job.phase == ExecutionPhase.COMPLETED
    assert job.results == [
        JobResult(id="greeting", url="https://example.com/Delay")
    ]

    # Run the shutdown hook.
    shutdown = settings.on_shutdown
    await shutdown(ctx)


@pytest.mark.asyncio
async def test_timeout(
    uws_config: UWSConfig,
    uws_factory: UWSFactory,
    test_token: str,
    test_username: str,
    logger: BoundLogger,
) -> None:
    job_service = uws_factory.create_job_service()
    redis_settings = uws_config.arq_redis_settings
    worker_config = WorkerConfig(
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

    # Create a job so that there is a Wobbly entry to update.
    await job_service.create(
        test_token, SimpleParameters(name="Timeout"), run_id="some-run-id"
    )

    # Run the worker.
    function = settings.functions[0].coroutine
    params = SimpleParameters(name="Timeout")
    info = WorkerJobInfo(
        job_id="1",
        job_url=f"{uws_config.wobbly_url}/jobs/1",
        user=test_username,
        token=test_token,
        timeout=timedelta(seconds=1),
        run_id="some-run-id",
    )
    assert await function(ctx, params, info) is None
    job = await job_service.get(test_token, "1")
    assert job.phase == ExecutionPhase.ERROR
    error = JobError(
        type=ErrorType.TRANSIENT,
        code="ServiceUnavailable",
        message="",
        detail=None,
    )
    error.message = ANY
    assert job.errors == [error]
    assert "Job timed out after" in job.errors[0].message

    # Make sure that handling the timeout didn't break the worker and we can
    # run another job successfully.
    await job_service.create(test_token, SimpleParameters(name="Roger"))
    params = SimpleParameters(name="Roger")
    info.job_id = "2"
    info.job_url = f"{uws_config.wobbly_url}/jobs/2"
    assert await function(ctx, params, info) is None
    job = await job_service.get(test_token, "2")
    assert job.results == [
        JobResult(id="greeting", url="https://example.com/Roger")
    ]

    # Run the shutdown hook.
    shutdown = settings.on_shutdown
    assert shutdown
    await shutdown(ctx)
