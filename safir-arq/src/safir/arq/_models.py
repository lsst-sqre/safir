"""Models used by the arq_ client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Self, override

from arq.jobs import Job, JobStatus

from ._exceptions import JobNotFound, JobResultUnavailable

__all__ = [
    "ArqMode",
    "JobMetadata",
    "JobResult",
]


class ArqMode(StrEnum):
    """Mode configuration for the Arq queue."""

    production = "production"
    """Normal usage of arq, with a Redis broker."""

    test = "test"
    """Use the MockArqQueue to test an API service without standing up a
    full distributed worker queue.
    """


@dataclass
class JobMetadata:
    """Information about a queued job."""

    id: str
    """The `~arq.jobs.Job` identifier."""

    name: str
    """The task name."""

    args: tuple[Any, ...]
    """The positional arguments to the task function."""

    kwargs: dict[str, Any]
    """The keyword arguments to the task function."""

    enqueue_time: datetime
    """Time when the job was added to the queue."""

    status: JobStatus
    """Status of the job.

    States are defined by the `arq.jobs.JobStatus` enumeration:

    - ``deferred`` (in queue, but waiting a predetermined time to become
      ready to run)
    - ``queued`` (queued to run)
    - ``in_progress`` (actively being run by a worker)
    - ``complete`` (result is available)
    - ``not_found`` (the job cannot be found)
    """

    queue_name: str
    """Name of the queue this job belongs to."""

    @classmethod
    async def from_job(cls, job: Job) -> Self:
        """Initialize JobMetadata from an arq Job.

        Raises
        ------
        JobNotFound
            Raised if the job is not found
        """
        job_info = await job.info()
        if job_info is None:
            raise JobNotFound(job.job_id)

        job_status = await job.status()
        if job_status == JobStatus.not_found:
            raise JobNotFound(job.job_id)

        return cls(
            id=job.job_id,
            name=job_info.function,
            args=job_info.args,
            kwargs=job_info.kwargs,
            enqueue_time=job_info.enqueue_time,
            status=job_status,
            # private attribute of Job; not available in JobDef
            # queue_name is available in JobResult
            queue_name=job._queue_name,  # noqa: SLF001
        )


@dataclass
class JobResult(JobMetadata):
    """The full result of a job, as well as its metadata."""

    start_time: datetime
    """Time when the job started."""

    finish_time: datetime
    """Time when the job finished."""

    success: bool
    """`True` if the job returned without an exception, `False` if an
    exception was raised.
    """

    result: Any
    """The job's result."""

    @override
    @classmethod
    async def from_job(cls, job: Job) -> Self:
        """Initialize the `JobResult` from an arq `~arq.jobs.Job`.

        Raises
        ------
        JobNotFound
            Raised if the job is not found
        JobResultUnavailable
            Raised if the job result is not available.
        """
        job_info = await job.info()
        if job_info is None:
            raise JobNotFound(job.job_id)

        job_status = await job.status()
        if job_status == JobStatus.not_found:
            raise JobNotFound(job.job_id)

        # Result may be none if the job isn't finished
        result_info = await job.result_info()
        if result_info is None:
            raise JobResultUnavailable(job.job_id)

        return cls(
            id=job.job_id,
            name=job_info.function,
            args=job_info.args,
            kwargs=job_info.kwargs,
            enqueue_time=job_info.enqueue_time,
            start_time=result_info.start_time,
            finish_time=result_info.finish_time,
            success=result_info.success,
            status=job_status,
            queue_name=result_info.queue_name,
            result=result_info.result,
        )
