"""Storage layer for the UWS implementation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from httpx import AsyncClient, Response
from pydantic import BaseModel
from vo_models.uws.types import ErrorType, ExecutionPhase

from safir.arq import JobMetadata
from safir.arq import JobResult as ArqJobResult
from safir.datetime import current_datetime

from ._config import UWSConfig
from ._exceptions import TaskError
from ._models import (
    Job,
    JobCreate,
    JobError,
    JobUpdateAborted,
    JobUpdateCompleted,
    JobUpdateError,
    JobUpdateExecuting,
    JobUpdateMetadata,
    JobUpdateQueued,
    ParametersModel,
    SerializedJob,
)

__all__ = ["JobStore"]


class JobStore:
    """Stores and manipulates jobs in the database.

    The canonical representation of any UWS job is in the database. This class
    provides methods to create, update, and delete UWS job records and their
    associated results and errors.

    Parameters
    ----------
    token
        Token for an individual user.
    config
        UWS configuration.
    http_client
        HTTP client to use to talk to Wobbly.
    """

    def __init__(
        self, token: str, config: UWSConfig, http_client: AsyncClient
    ) -> None:
        self._token = token
        self._config = config
        self._client = http_client
        self._base_url = str(config.wobbly_url).rstrip("/")

    async def create(
        self,
        *,
        run_id: str | None = None,
        parameters: ParametersModel,
        execution_duration: timedelta,
        lifetime: timedelta,
    ) -> Job:
        """Create a record of a new job.

        The job will be created in pending status.

        Parameters
        ----------
        run_id
            A client-supplied opaque identifier to record with the job.
        parameters
            The input parameters to the job.
        execution_duration
            The maximum length of time for which a job is allowed to run in
            seconds.
        lifetime
            The maximum lifetime of the job and its results, in seconds.
            After this time, any record of the job will be deleted.

        Returns
        -------
        Job
            Newly-created job.
        """
        job_create = JobCreate(
            json_parameters=parameters.model_dump(mode="json"),
            run_id=run_id,
            destruction_time=current_datetime() + lifetime,
            execution_duration=execution_duration,
        )
        r = await self._request("POST", "jobs", job_create)
        job = SerializedJob.model_validate(r.json())
        return Job.from_serialized_job(job, self._config.parameters_type)

    async def delete(self, job_id: str) -> None:
        """Delete a job by ID."""
        await self._request("DELETE", f"jobs/{job_id}")

    async def get(self, job_id: str) -> Job:
        """Retrieve a job by ID."""
        r = await self._request("GET", f"jobs/{job_id}")
        job = SerializedJob.model_validate(r.json())
        return Job.from_serialized_job(job, self._config.parameters_type)

    async def list_jobs(
        self,
        *,
        phases: Iterable[ExecutionPhase] | None = None,
        after: datetime | None = None,
        count: int | None = None,
    ) -> list[SerializedJob]:
        """List the jobs for a particular user.

        Parameters
        ----------
        phases
            Limit the result to jobs in this list of possible execution
            phases.
        after
            Limit the result to jobs created after the given datetime in UTC.
        count
            Limit the results to the most recent count jobs.

        Returns
        -------
        list of SerializedJob
            List of job descriptions matching the search criteria.
        """
        query: list[tuple[str, str]] = []
        if phases:
            query.extend(("phase", str(p)) for p in phases)
        if after:
            query.append(("since", after.isoformat()))
        if count:
            query.append(("limit", str(count)))
        r = await self._request("GET", "jobs", query=query)
        return [SerializedJob.model_validate(j) for j in r.json()]

    async def mark_aborted(self, job_id: str) -> None:
        """Mark a job as aborted.

        Parameters
        ----------
        job_id
            Identifier of the job.
        """
        await self._request(
            "PATCH",
            f"jobs/{job_id}",
            JobUpdateAborted(phase=ExecutionPhase.ABORTED),
        )

    async def mark_completed(
        self, job_id: str, job_result: ArqJobResult
    ) -> None:
        """Mark a job as completed.

        Parameters
        ----------
        job_id
            Identifier of the job.
        job_result
            Result of the job.
        """
        if isinstance(job_result.result, Exception):
            await self.mark_failed(job_id, job_result.result)
            return
        update = JobUpdateCompleted(
            phase=ExecutionPhase.COMPLETED, results=job_result.result
        )
        await self._request("PATCH", f"jobs/{job_id}", update)

    async def mark_failed(self, job_id: str, exc: Exception) -> None:
        """Mark a job as failed with an error.

        Currently, only one error is supported, even though Wobbly supports
        associating multiple errors with a job.

        Parameters
        ----------
        job_id
            Identifier of the job.
        exc
            Exception of failed job.
        """
        if isinstance(exc, TaskError):
            error = exc.to_job_error()
        else:
            error = JobError(
                type=ErrorType.FATAL,
                code="Error",
                message="Unknown error executing task",
                detail=f"{type(exc).__name__}: {exc!s}",
            )
        update = JobUpdateError(phase=ExecutionPhase.ERROR, errors=[error])
        await self._request("PATCH", f"jobs/{job_id}", update)

    async def mark_executing(self, job_id: str, start_time: datetime) -> None:
        """Mark a job as executing.

        Parameters
        ----------
        job_id
            Identifier of the job.
        start_time
            Time at which the job started executing.
        """
        update = JobUpdateExecuting(
            phase=ExecutionPhase.EXECUTING, start_time=start_time
        )
        await self._request("PATCH", f"jobs/{job_id}", update)

    async def mark_queued(self, job_id: str, metadata: JobMetadata) -> None:
        """Mark a job as queued for processing.

        This is called by the web frontend after queuing the work. However,
        the worker may have gotten there first and have already updated the
        phase to executing, in which case we should not set it back to queued.

        Parameters
        ----------
        job_id
            Identifier of the job.
        metadata
            Metadata about the underlying arq job.
        """
        update = JobUpdateQueued(
            phase=ExecutionPhase.QUEUED, message_id=metadata.id
        )
        await self._request("PATCH", f"jobs/{job_id}", update)

    async def update_metadata(
        self,
        job_id: str,
        destruction: datetime,
        execution_duration: timedelta | None,
    ) -> None:
        """Update the destruction time or execution duration of a job.

        Parameters
        ----------
        job_id
            Identifier of the job.
        destruction
            New destruction time.
        execution_duration
            New execution duration.
        """
        update = JobUpdateMetadata(
            destruction_time=destruction, execution_duration=execution_duration
        )
        await self._request("PATCH", f"jobs/{job_id}", update)

    async def _request(
        self,
        method: str,
        route: str,
        body: BaseModel | None = None,
        *,
        query: list[tuple[str, str]] | None = None,
    ) -> Response:
        """Send an HTTP request to Wobbly.

        Parameters
        ----------
        method
            HTTP method.
        route
            Route, relative to the base URL of Wobbly.
        body
            If given, a Pydantic model that should be serialized bo create the
            JSON body of the request.
        query
            If given, query parameters to send.

        Returns
        -------
        Response
            HTTP response object.

        Raises
        ------
        httpx.HTTPError
            Raised if the HTTP request fails or returns a failure status.
        """
        kwargs: dict[str, Any] = {
            "headers": {"Authorization": f"bearer {self._token}"}
        }
        if body:
            kwargs["json"] = body.model_dump(mode="json")
        if query:
            kwargs["params"] = query
        url = self._base_url + "/" + route
        r = await self._client.request(method, url, **kwargs)
        r.raise_for_status()
        return r
