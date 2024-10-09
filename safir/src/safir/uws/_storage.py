"""Storage layer for the UWS implementation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ParamSpec, TypeVar

from sqlalchemy import delete
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.future import select
from vo_models.uws.types import ErrorType, ExecutionPhase
from vo_models.vosi.availability import Availability

from safir.arq import JobMetadata, JobResult
from safir.database import (
    datetime_from_db,
    datetime_to_db,
    retry_async_transaction,
)
from safir.datetime import current_datetime

from ._exceptions import TaskError, UnknownJobError
from ._models import (
    ErrorCode,
    UWSJob,
    UWSJobDescription,
    UWSJobError,
    UWSJobParameter,
    UWSJobResult,
)
from ._schema import Job as SQLJob
from ._schema import JobParameter as SQLJobParameter
from ._schema import JobResult as SQLJobResult

T = TypeVar("T")
P = ParamSpec("P")

__all__ = ["JobStore"]


def _convert_job(job: SQLJob) -> UWSJob:
    """Convert the SQL representation of a job to its dataclass.

    The internal representation of a job uses a dataclass that is kept
    intentionally separate from the database schema so that the conversion can
    be done explicitly and the rest of the code kept separate from SQLAlchemy
    database models. This internal helper function converts from the database
    representation to the internal representation.
    """
    error = None
    if job.error_code and job.error_type and job.error_message:
        error = UWSJobError(
            error_type=job.error_type,
            error_code=job.error_code,
            message=job.error_message,
            detail=job.error_detail,
        )
    return UWSJob(
        job_id=str(job.id),
        message_id=job.message_id,
        owner=job.owner,
        phase=job.phase,
        run_id=job.run_id,
        creation_time=datetime_from_db(job.creation_time),
        start_time=datetime_from_db(job.start_time),
        end_time=datetime_from_db(job.end_time),
        destruction_time=datetime_from_db(job.destruction_time),
        execution_duration=timedelta(seconds=job.execution_duration),
        quote=job.quote,
        parameters=[
            UWSJobParameter(parameter_id=p.parameter, value=p.value)
            for p in sorted(job.parameters, key=lambda p: p.id)
        ],
        results=[
            UWSJobResult(
                result_id=r.result_id,
                url=r.url,
                size=r.size,
                mime_type=r.mime_type,
            )
            for r in sorted(job.results, key=lambda r: r.sequence)
        ],
        error=error,
    )


class JobStore:
    """Stores and manipulates jobs in the database.

    The canonical representation of any UWS job is in the database. This class
    provides methods to create, update, and delete UWS job records and their
    associated results and errors.

    Parameters
    ----------
    session
        The underlying database session.
    """

    def __init__(self, session: async_scoped_session) -> None:
        self._session = session

    async def add(
        self,
        *,
        owner: str,
        run_id: str | None = None,
        params: list[UWSJobParameter],
        execution_duration: timedelta,
        lifetime: timedelta,
    ) -> UWSJob:
        """Create a record of a new job.

        The job will be created in pending status.

        Parameters
        ----------
        owner
            The username of the owner of the job.
        run_id
            A client-supplied opaque identifier to record with the job.
        params
            The input parameters to the job.
        execution_duration
            The maximum length of time for which a job is allowed to run in
            seconds.
        lifetime
            The maximum lifetime of the job and its results, in seconds.
            After this time, any record of the job will be deleted.

        Returns
        -------
        safir.uws._models.Job
            The internal representation of the newly-created job.
        """
        now = current_datetime()
        destruction_time = now + lifetime
        sql_params = [
            SQLJobParameter(parameter=p.parameter_id, value=p.value)
            for p in params
        ]
        job = SQLJob(
            owner=owner,
            phase=ExecutionPhase.PENDING,
            run_id=run_id,
            creation_time=datetime_to_db(now),
            destruction_time=datetime_to_db(destruction_time),
            execution_duration=int(execution_duration.total_seconds()),
            parameters=sql_params,
            results=[],
        )
        async with self._session.begin():
            self._session.add_all([job, *sql_params])
            await self._session.flush()
            return _convert_job(job)

    async def availability(self) -> Availability:
        """Check that the database is up."""
        try:
            async with self._session.begin():
                await self._session.execute(select(SQLJob.id).limit(1))
            return Availability(available=True)
        except OperationalError:
            note = "cannot query UWS job database"
            return Availability(available=False, note=[note])
        except Exception as e:
            note = f"{type(e).__name__}: {e!s}"
            return Availability(available=False, note=[note])

    async def delete(self, job_id: str) -> None:
        """Delete a job by ID."""
        stmt = delete(SQLJob).where(SQLJob.id == int(job_id))
        async with self._session.begin():
            await self._session.execute(stmt)

    async def get(self, job_id: str) -> UWSJob:
        """Retrieve a job by ID."""
        async with self._session.begin():
            job = await self._get_job(job_id)
            return _convert_job(job)

    async def list_expired(self) -> list[UWSJobDescription]:
        """Delete all jobs that have passed their destruction time."""
        now = datetime_to_db(current_datetime())
        stmt = select(
            SQLJob.id,
            SQLJob.message_id,
            SQLJob.owner,
            SQLJob.phase,
            SQLJob.run_id,
            SQLJob.creation_time,
        ).where(SQLJob.destruction_time <= now)
        async with self._session.begin():
            jobs = await self._session.execute(stmt)
            return [
                UWSJobDescription(
                    job_id=str(j.id),
                    message_id=j.message_id,
                    owner=j.owner,
                    phase=j.phase,
                    run_id=j.run_id,
                    creation_time=datetime_from_db(j.creation_time),
                )
                for j in jobs.all()
            ]

    async def list_jobs(
        self,
        user: str,
        *,
        phases: list[ExecutionPhase] | None = None,
        after: datetime | None = None,
        count: int | None = None,
    ) -> list[UWSJobDescription]:
        """List the jobs for a particular user.

        Parameters
        ----------
        user
            Name of the user whose jobs to load.
        phases
            Limit the result to jobs in this list of possible execution
            phases.
        after
            Limit the result to jobs created after the given datetime in UTC.
        count
            Limit the results to the most recent count jobs.

        Returns
        -------
        list of safir.uws._models.JobDescription
            List of job descriptions matching the search criteria.
        """
        stmt = select(
            SQLJob.id,
            SQLJob.message_id,
            SQLJob.owner,
            SQLJob.phase,
            SQLJob.run_id,
            SQLJob.creation_time,
        ).where(SQLJob.owner == user)
        if phases:
            stmt = stmt.where(SQLJob.phase.in_(phases))
        if after:
            stmt = stmt.where(SQLJob.creation_time > datetime_to_db(after))
        stmt = stmt.order_by(SQLJob.creation_time.desc())
        if count:
            stmt = stmt.limit(count)
        async with self._session.begin():
            jobs = await self._session.execute(stmt)
            return [
                UWSJobDescription(
                    job_id=str(j.id),
                    message_id=j.message_id,
                    owner=j.owner,
                    phase=j.phase,
                    run_id=j.run_id,
                    creation_time=datetime_from_db(j.creation_time),
                )
                for j in jobs.all()
            ]

    @retry_async_transaction
    async def mark_aborted(self, job_id: str) -> None:
        """Mark a job as aborted.

        Parameters
        ----------
        job_id
            Identifier of the job.
        """
        async with self._session.begin():
            job = await self._get_job(job_id)
            job.phase = ExecutionPhase.ABORTED
            if job.start_time:
                job.end_time = datetime_to_db(current_datetime())

    @retry_async_transaction
    async def mark_completed(self, job_id: str, job_result: JobResult) -> None:
        """Mark a job as completed.

        Parameters
        ----------
        job_id
            Identifier of the job.
        job_result
            Result of the job.
        """
        end_time = job_result.finish_time.replace(microsecond=0)
        results = job_result.result
        if isinstance(results, Exception):
            await self.mark_failed(job_id, results, end_time=end_time)
            return

        async with self._session.begin():
            job = await self._get_job(job_id)
            job.end_time = datetime_to_db(end_time)
            if job.phase != ExecutionPhase.ABORTED:
                job.phase = ExecutionPhase.COMPLETED
                for sequence, result in enumerate(results, start=1):
                    sql_result = SQLJobResult(
                        job_id=job.id,
                        result_id=result.result_id,
                        sequence=sequence,
                        url=result.url,
                        size=result.size,
                        mime_type=result.mime_type,
                    )
                    self._session.add(sql_result)

    @retry_async_transaction
    async def mark_failed(
        self, job_id: str, exc: Exception, *, end_time: datetime | None = None
    ) -> None:
        """Mark a job as failed with an error.

        Parameters
        ----------
        job_id
            Identifier of the job.
        exc
            Exception of failed job.
        end_time
            When the job failed, if known.
        """
        if isinstance(exc, TaskError):
            error = exc.to_job_error()
        else:
            error = UWSJobError(
                error_type=ErrorType.FATAL,
                error_code=ErrorCode.ERROR,
                message="Unknown error executing task",
                detail=f"{type(exc).__name__}: {exc!s}",
            )
        async with self._session.begin():
            job = await self._get_job(job_id)
            job.end_time = datetime_to_db(end_time or current_datetime())
            if job.phase != ExecutionPhase.ABORTED:
                job.phase = ExecutionPhase.ERROR
                job.error_type = error.error_type
                job.error_code = error.error_code
                job.error_message = error.message
                job.error_detail = error.detail

    @retry_async_transaction
    async def mark_executing(self, job_id: str, start_time: datetime) -> None:
        """Mark a job as executing.

        Parameters
        ----------
        job_id
            Identifier of the job.
        start_time
            Time at which the job started executing.
        """
        start_time = start_time.replace(microsecond=0)
        async with self._session.begin():
            job = await self._get_job(job_id)
            if job.phase in (ExecutionPhase.PENDING, ExecutionPhase.QUEUED):
                job.phase = ExecutionPhase.EXECUTING
            job.start_time = datetime_to_db(start_time)

    @retry_async_transaction
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
        async with self._session.begin():
            job = await self._get_job(job_id)
            job.message_id = metadata.id
            if job.phase in (ExecutionPhase.PENDING, ExecutionPhase.HELD):
                job.phase = ExecutionPhase.QUEUED

    async def update_destruction(
        self, job_id: str, destruction: datetime
    ) -> None:
        """Update the destruction time of a job.

        Parameters
        ----------
        job_id
            Identifier of the job.
        destruction
            New destruction time.
        """
        destruction = destruction.replace(microsecond=0)
        async with self._session.begin():
            job = await self._get_job(job_id)
            job.destruction_time = datetime_to_db(destruction)

    async def update_execution_duration(
        self, job_id: str, execution_duration: timedelta
    ) -> None:
        """Update the destruction time of a job.

        Parameters
        ----------
        job_id
            Identifier of the job.
        execution_duration
            New execution duration.
        """
        async with self._session.begin():
            job = await self._get_job(job_id)
            job.execution_duration = int(execution_duration.total_seconds())

    async def _get_job(self, job_id: str) -> SQLJob:
        """Retrieve a job from the database by job ID."""
        stmt = select(SQLJob).where(SQLJob.id == int(job_id))
        job = (await self._session.execute(stmt)).scalar_one_or_none()
        if not job:
            raise UnknownJobError(job_id)
        return job
