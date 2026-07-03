"""Test synchronous UWS job execution."""

import asyncio

import pytest
from httpx import AsyncClient

from safir.arq.uws import WorkerResult, WorkerUsageError
from safir.testing.uws import MockUWSJobRunner
from safir.uws._exceptions import TaskError


@pytest.mark.asyncio
async def test_sync(
    client: AsyncClient,
    test_token: str,
    runner: MockUWSJobRunner,
) -> None:
    results = [
        WorkerResult(
            result_id="cutout",
            url="s3://some-bucket/some/path",
            mime_type="application/fits",
        )
    ]

    # Start sync POST and GET requests.
    task_post = asyncio.create_task(
        client.post("/test/sync", data={"name": "Jane"})
    )
    task_get = asyncio.create_task(
        client.get("/test/sync", params={"name": "Jane"})
    )
    await asyncio.sleep(0.1)

    # Tell the queue the jobs are finished.
    for job_id in ("1", "2"):
        await runner.mark_complete(test_token, job_id, results)

    # The sync request tasks should now return a redirect response to the
    # proper fake signed URL.
    for task in (task_post, task_get):
        r = await task
        assert r.status_code == 303
        assert r.headers["Location"] == "https://example.com/some/path"


@pytest.mark.asyncio
async def test_sync_usage_error(
    client: AsyncClient,
    test_token: str,
    runner: MockUWSJobRunner,
) -> None:
    task = asyncio.create_task(
        client.post("/test/sync", data={"name": "Jane"})
    )
    await asyncio.sleep(0.1)

    # Register a failure with a usage error.
    exc = WorkerUsageError("Some usage error")
    result = TaskError.from_worker_error(exc)
    await runner.mark_complete(test_token, "1", result)

    # This should return a 422 error with the correct body.
    r = await task
    assert r.text == "UsageError: Some usage error\n"
    assert r.status_code == 422
