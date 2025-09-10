"""Storage layer for the UWS implementation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from httpx import AsyncClient, HTTPError, Response
from pydantic import BaseModel
from vo_models.uws.types import ErrorType, ExecutionPhase

from safir.arq import JobMetadata
from safir.arq import JobResult as ArqJobResult
from safir.datetime import current_datetime, isodatetime

from ._config import UWSConfig
from ._exceptions import TaskError, UnknownJobError, WobblyError
from ._models import (
    Job,
    JobCreate,
    JobError,
    JobResult,
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
    config
        UWS configuration.
    http_client
        HTTP client to use to talk to Wobbly.
    """

    def __init__(self, config: UWSConfig, http_client: AsyncClient) -> None:
        self._config = config
        self._client = http_client
        self._base_url = str(config.wobbly_url).rstrip("/")

    async def create(
        self,
        token: str,
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
        token
            Token for an individual user.
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

        Raises
        ------
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job_create = JobCreate(
            json_parameters=parameters.model_dump(mode="json"),
            run_id=run_id,
            destruction_time=current_datetime() + lifetime,
            execution_duration=execution_duration,
        )
        r = await self._request("POST", token, body=job_create)
        job = SerializedJob.model_validate(r.json())
        return Job.from_serialized_job(job, self._config.parameters_type)

    async def delete(self, token: str, job_id: str) -> None:
        """Delete a job by ID.

        Parameters
        ----------
        token
            Token for an individual user.
        job_id
            Job ID to delete.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        await self._request("DELETE", token, job_id)

    async def get(self, token: str, job_id: str) -> Job:
        """Retrieve a job by ID.

        Parameters
        ----------
        token
            Token for an individual user.
        job_id
            Job ID to retrieve.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        r = await self._request("GET", token, job_id)
        job = SerializedJob.model_validate(r.json())
        return Job.from_serialized_job(job, self._config.parameters_type)

    async def list_jobs(
        self,
        token: str,
        *,
        phases: Iterable[ExecutionPhase] | None = None,
        after: datetime | None = None,
        count: int | None = None,
    ) -> list[SerializedJob]:
        """List the jobs for a particular user.

        Parameters
        ----------
        token
            Token for an individual user.
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

        Raises
        ------
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        query: list[tuple[str, str]] = []
        if phases:
            query.extend(("phase", p.value) for p in phases)
        if after:
            query.append(("since", isodatetime(after)))
        if count:
            query.append(("limit", str(count)))
        r = await self._request("GET", token, query=query)
        return [SerializedJob.model_validate(j) for j in r.json()]

    async def mark_aborted(self, token: str, job_id: str) -> None:
        """Mark a job as aborted.

        Parameters
        ----------
        token
            Token for an individual user.
        job_id
            Identifier of the job.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        update = JobUpdateAborted(phase=ExecutionPhase.ABORTED)
        await self._request("PATCH", token, job_id, body=update)

    async def mark_completed(
        self, token: str, job_id: str, job_result: ArqJobResult
    ) -> None:
        """Mark a job as completed.

        Parameters
        ----------
        token
            Token for an individual user.
        job_id
            Identifier of the job.
        job_result
            Result of the job.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        if isinstance(job_result.result, Exception):
            await self.mark_failed(token, job_id, job_result.result)
            return
        results = [JobResult.from_worker_result(r) for r in job_result.result]
        update = JobUpdateCompleted(
            phase=ExecutionPhase.COMPLETED, results=results
        )
        await self._request("PATCH", token, job_id, body=update)

    async def mark_failed(
        self, token: str, job_id: str, exc: Exception
    ) -> None:
        """Mark a job as failed with an error.

        Currently, only one error is supported, even though Wobbly supports
        associating multiple errors with a job.

        Parameters
        ----------
        token
            Token for an individual user.
        job_id
            Identifier of the job.
        exc
            Exception of failed job.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
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
        await self._request("PATCH", token, job_id, body=update)

    async def mark_executing(
        self, token: str, job_id: str, start_time: datetime
    ) -> None:
        """Mark a job as executing.

        Parameters
        ----------
        token
            Token for an individual user.
        job_id
            Identifier of the job.
        start_time
            Time at which the job started executing.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        update = JobUpdateExecuting(
            phase=ExecutionPhase.EXECUTING, start_time=start_time
        )
        await self._request("PATCH", token, job_id, body=update)

    async def mark_queued(
        self, token: str, job_id: str, metadata: JobMetadata
    ) -> None:
        """Mark a job as queued for processing.

        Parameters
        ----------
        token
            Token for an individual user.
        job_id
            Identifier of the job.
        metadata
            Metadata about the underlying arq job.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        update = JobUpdateQueued(
            phase=ExecutionPhase.QUEUED, message_id=metadata.id
        )
        await self._request("PATCH", token, job_id, body=update)

    async def update_metadata(
        self,
        token: str,
        job_id: str,
        metadata: JobUpdateMetadata,
    ) -> None:
        """Update the destruction time or execution duration of a job.

        Parameters
        ----------
        token
            Token for an individual user.
        job_id
            Identifier of the job.
        metadata
            New job metadata.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        await self._request("PATCH", token, job_id, body=metadata)

    async def _request(
        self,
        method: str,
        token: str,
        job_id: str | None = None,
        *,
        body: BaseModel | None = None,
        query: list[tuple[str, str]] | None = None,
    ) -> Response:
        """Send an HTTP request to Wobbly.

        Parameters
        ----------
        method
            HTTP method.
        token
            Token for an individual user.
        job_id
            Identifier of job to act on.
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
        UnknownJobError
            Raised if the request was for a specific job and that job was not
            found.
        WobblyError
            Raised if the HTTP request fails or returns a failure status.
        """
        kwargs: dict[str, Any] = {
            "headers": {"Authorization": f"bearer {token}"}
        }
        if body:
            kwargs["json"] = body.model_dump(mode="json")
        if query:
            kwargs["params"] = query
        url = self._base_url + "/jobs"
        if job_id:
            url += "/" + job_id
        try:
            r = await self._client.request(method, url, **kwargs)
            if r.status_code == 404 and job_id:
                raise UnknownJobError(job_id)
            r.raise_for_status()
        except HTTPError as e:
            raise WobblyError.from_exception(e) from e
        return r
