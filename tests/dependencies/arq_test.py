"""Test `safir.dependencies.arq`."""

from __future__ import annotations

from typing import Any, Optional

import pytest
from arq.constants import default_queue_name
from asgi_lifespan import LifespanManager
from fastapi import Depends, FastAPI, HTTPException
from httpx import AsyncClient

from safir.arq import ArqMode, JobNotFound, JobResultUnavailable, MockArqQueue
from safir.dependencies.arq import arq_dependency


@pytest.mark.asyncio
async def test_arq_dependency_mock() -> None:
    """Test the arq dependency entirely through the MockArqQueue."""
    app = FastAPI()

    @app.post("/")
    async def post_job(
        arq_queue: MockArqQueue = Depends(arq_dependency),
    ) -> dict[str, Any]:
        """Create a job."""
        job = await arq_queue.enqueue("test_task", "hello", a_number=42)
        return {
            "job_id": job.id,
            "job_status": job.status,
            "job_name": job.name,
            "job_args": job.args,
            "job_kwargs": job.kwargs,
            "job_queue_name": job.queue_name,
        }

    @app.get("/jobs/{job_id}")
    async def get_metadata(
        job_id: str,
        queue_name: Optional[str] = None,
        arq_queue: MockArqQueue = Depends(arq_dependency),
    ) -> dict[str, Any]:
        """Get metadata about a job."""
        try:
            job = await arq_queue.get_job_metadata(
                job_id, queue_name=queue_name
            )
        except JobNotFound:
            raise HTTPException(status_code=404)
        return {
            "job_id": job.id,
            "job_status": job.status,
            "job_name": job.name,
            "job_args": job.args,
            "job_kwargs": job.kwargs,
            "job_queue_name": job.queue_name,
        }

    @app.get("/results/{job_id}")
    async def get_result(
        job_id: str,
        queue_name: Optional[str] = None,
        arq_queue: MockArqQueue = Depends(arq_dependency),
    ) -> dict[str, Any]:
        """Get the results for a job."""
        try:
            job_result = await arq_queue.get_job_result(
                job_id, queue_name=queue_name
            )
        except (JobNotFound, JobResultUnavailable) as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {
            "job_id": job_result.id,
            "job_status": job_result.status,
            "job_name": job_result.name,
            "job_args": job_result.args,
            "job_kwargs": job_result.kwargs,
            "job_queue_name": job_result.queue_name,
            "job_result": job_result.result,
            "job_success": job_result.success,
        }

    @app.post("/jobs/{job_id}/inprogress")
    async def post_job_inprogress(
        job_id: str,
        queue_name: Optional[str] = None,
        arq_queue: MockArqQueue = Depends(arq_dependency),
    ) -> None:
        """Toggle a job to in-progress, for testing."""
        try:
            await arq_queue.set_in_progress(job_id, queue_name=queue_name)
        except JobNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/jobs/{job_id}/complete")
    async def post_job_complete(
        job_id: str,
        queue_name: Optional[str] = None,
        result: Optional[str] = None,
        success: bool = True,
        arq_queue: MockArqQueue = Depends(arq_dependency),
    ) -> None:
        """Toggle a job to complete, for testing."""
        try:
            await arq_queue.set_complete(
                job_id, result=result, success=success, queue_name=queue_name
            )
        except JobNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.on_event("startup")
    async def startup() -> None:
        await arq_dependency.initialize(mode=ArqMode.test, redis_settings=None)

    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://example.com") as c:
            r = await c.post("/")
            assert r.status_code == 200
            data = r.json()
            job_id = data["job_id"]
            assert data["job_status"] == "queued"
            assert data["job_name"] == "test_task"
            assert data["job_args"] == ["hello"]
            assert data["job_kwargs"] == {"a_number": 42}
            assert data["job_queue_name"] == default_queue_name

            r = await c.get(f"/jobs/{job_id}")
            assert r.status_code == 200
            assert data["job_kwargs"] == {"a_number": 42}

            # Wrong queue name
            r = await c.get(f"/jobs/{job_id}?queue_name=queue2")
            assert r.status_code == 404

            # Result should not be available
            r = await c.get(f"/results/{job_id}")
            assert r.status_code == 404
            data = r.json()
            assert data["detail"] == (
                f"Job result could not be found. id={job_id}"
            )

            # Set to in-progress
            r = await c.post(f"/jobs/{job_id}/inprogress")
            r = await c.get(f"/jobs/{job_id}")
            data = r.json()
            assert data["job_status"] == "in_progress"

            # Set to successful completion
            r = await c.post(f"/jobs/{job_id}/complete?result=done")
            r = await c.get(f"/results/{job_id}")
            assert r.status_code == 200
            data = r.json()
            assert data["job_status"] == "complete"
            assert data["job_result"] == "done"
            assert data["job_success"] is True
