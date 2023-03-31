"""An `arq <https://arq-docs.helpmanual.io>`__ client with a mock for
testing.
"""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Self

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.constants import default_queue_name as arq_default_queue_name
from arq.jobs import Job, JobStatus

__all__ = [
    "ArqJobError",
    "JobNotQueued",
    "JobNotFound",
    "JobResultUnavailable",
    "ArqMode",
    "JobMetadata",
    "JobResult",
    "ArqQueue",
    "RedisArqQueue",
    "MockArqQueue",
]


class ArqJobError(Exception):
    """A base class for errors related to arq jobs.

    Attributes
    ----------
    job_id
        The job ID, or `None` if the job ID is not known in this context.
    """

    def __init__(self, message: str, job_id: str | None) -> None:
        super().__init__(message)
        self._job_id = job_id

    @property
    def job_id(self) -> str | None:
        """The job ID, or `None` if the job ID is not known in this context."""
        return self._job_id


class JobNotQueued(ArqJobError):
    """The job was not successfully queued."""

    def __init__(self, job_id: str | None) -> None:
        super().__init__(
            f"Job was not queued because it already exists. id={job_id}",
            job_id,
        )


class JobNotFound(ArqJobError):
    """A job cannot be found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job could not be found. id={job_id}", job_id)


class JobResultUnavailable(ArqJobError):
    """The job's result is unavailable."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job result could not be found. id={job_id}", job_id)


class ArqMode(str, Enum):
    """Mode configuration for the Arq queue."""

    production = "production"
    """Normal usage of arq, with a Redis broker."""

    test = "test"
    """Use the MockArqQueue to test an API service without standing up a
    full distributed worker queue.
    """


@dataclass
class JobMetadata:
    """Information about a queued job.

    Attributes
    ----------
    id
        The `arq.jobs.Job` identifier
    name
        The task name.
    args
        The positional arguments to the task function.
    kwargs
        The keyword arguments to the task function.
    enqueue_time
        Time when the job was added to the queue.
    status
        Status of the job.

        States are defined by the `arq.jobs.JobStatus` enumeration:

        - ``deferred`` (in queue, but waiting a predetermined time to become
          ready to run)
        - ``queued`` (queued to run)
        - ``in_progress`` (actively being run by a worker)
        - ``complete`` (result is available)
        - ``not_found`` (the job cannot be found)
    queue_name
        Name of the queue this job belongs to.
    """

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
            queue_name=job._queue_name,
        )


@dataclass
class JobResult(JobMetadata):
    """The full result of a job, as well as its metadata.

    Attributes
    ----------
    id
        The `~arq.jobs.Job` identifier
    name
        The task name.
    args
        The positional arguments to the task function.
    kwargs
        The keyword arguments to the task function.
    enqueue_time
        Time when the job was added to the queue.
    status
        Status of the job.

        States are defined by the `arq.jobs.JobStatus` enumeration:

        - ``deferred`` (in queue, but waiting a predetermined time to become
          ready to run)
        - ``queued`` (queued to run)
        - ``in_progress`` (actively being run by a worker)
        - ``complete`` (result is available)
        - ``not_found`` (the job cannot be found)
    start_time
        Time when the job started.
    finish_time
        Time when the job finished.
    success
        `True` if the job returned without an exception, `False` if an
        exception was raised.
    result
        The job's result.
    """

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


class ArqQueue(metaclass=abc.ABCMeta):
    """An common interface for working with an arq queue that can be
    implemented either with a real Redis backend, or an in-memory repository
    for testing.

    See also
    --------
    RedisArqQueue
        Production implementation with a Redis store.
    MockArqQueue
        In-memory implementation for testing and development.
    """

    def __init__(
        self, *, default_queue_name: str = arq_default_queue_name
    ) -> None:
        self._default_queue_name = default_queue_name

    @property
    def default_queue_name(self) -> str:
        """Name of the default queue, if the ``_queue_name`` parameter is
        no set in method calls.
        """
        return self._default_queue_name

    @abc.abstractmethod
    async def enqueue(
        self,
        task_name: str,
        *task_args: Any,
        _queue_name: Optional[str] = None,
        **task_kwargs: Any,
    ) -> JobMetadata:
        """Add a job to the queue.

        Parameters
        ----------
        task_name
            The function name to run.
        *args
            Positional arguments for the task function.
        _queue_name
            Name of the queue.
        **kwargs
            Keyword arguments passed to the task function.

        Returns
        -------
        JobMetadata
            Metadata about the queued job.

        Raises
        ------
        JobNotQueued
            Raised if the job is not successfully added to the queue.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_job_metadata(
        self, job_id: str, queue_name: Optional[str] = None
    ) -> JobMetadata:
        """Get metadata about a `~arq.jobs.Job`.

        Parameters
        ----------
        job_id
            The job's identifier. This is the same as the `JobMetadata.id`
            attribute, provided when initially adding a job to the queue.
        queue_name
            Name of the queue.

        Returns
        -------
        JobMetadata
            Metadata about the queued job.

        Raises
        ------
        JobNotFound
            Raised if the job is not found in the queue.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_job_result(
        self, job_id: str, queue_name: Optional[str] = None
    ) -> JobResult:
        """The job result, if available.

        Parameters
        ----------
        job_id
            The job's identifier. This is the same as the `JobMetadata.id`
            attribute, provided when initially adding a job to the queue.
        queue_name
            Name of the queue.

        Returns
        -------
        JobResult
            The job's result, along with metadata about the queued job.

        Raises
        ------
        JobNotFound
            Raised if the job is not found in the queue.
        JobResultUnavailable
            Raised if the job's result is unavailable for any reason.
        """
        raise NotImplementedError


class RedisArqQueue(ArqQueue):
    """A distributed queue, based on arq and Redis."""

    def __init__(
        self,
        pool: ArqRedis,
        *,
        default_queue_name: str = arq_default_queue_name,
    ) -> None:
        super().__init__(default_queue_name=default_queue_name)
        self._pool = pool

    @classmethod
    async def initialize(
        cls,
        redis_settings: RedisSettings,
        *,
        default_queue_name: str = arq_default_queue_name,
    ) -> Self:
        """Initialize a RedisArqQueue from Redis settings."""
        pool = await create_pool(
            redis_settings, default_queue_name=default_queue_name
        )
        return cls(pool)

    async def enqueue(
        self,
        task_name: str,
        *task_args: Any,
        _queue_name: Optional[str] = None,
        **task_kwargs: Any,
    ) -> JobMetadata:
        job = await self._pool.enqueue_job(
            task_name,
            *task_args,
            _queue_name=_queue_name or self.default_queue_name,
            **task_kwargs,
        )
        if job:
            return await JobMetadata.from_job(job)
        else:
            # TODO if implementing hard-coded job IDs, set as an argument
            raise JobNotQueued(None)

    def _get_job(self, job_id: str, queue_name: Optional[str] = None) -> Job:
        return Job(
            job_id,
            self._pool,
            _queue_name=queue_name or self.default_queue_name,
        )

    async def get_job_metadata(
        self, job_id: str, queue_name: Optional[str] = None
    ) -> JobMetadata:
        job = self._get_job(job_id, queue_name=queue_name)
        return await JobMetadata.from_job(job)

    async def get_job_result(
        self, job_id: str, queue_name: Optional[str] = None
    ) -> JobResult:
        job = self._get_job(job_id, queue_name=queue_name)
        return await JobResult.from_job(job)


class MockArqQueue(ArqQueue):
    """A mocked queue for testing API services."""

    def __init__(
        self, *, default_queue_name: str = arq_default_queue_name
    ) -> None:
        super().__init__(default_queue_name=default_queue_name)
        self._job_metadata: dict[str, dict[str, JobMetadata]] = {
            self.default_queue_name: {}
        }
        self._job_results: dict[str, dict[str, JobResult]] = {
            self.default_queue_name: {}
        }

    def _resolve_queue_name(self, queue_name: str | None) -> str:
        return queue_name or self.default_queue_name

    async def enqueue(
        self,
        task_name: str,
        *task_args: Any,
        _queue_name: Optional[str] = None,
        **task_kwargs: Any,
    ) -> JobMetadata:
        queue_name = self._resolve_queue_name(_queue_name)
        new_job = JobMetadata(
            id=str(uuid.uuid4().hex),
            name=task_name,
            args=task_args,
            kwargs=task_kwargs,
            enqueue_time=datetime.now(),
            status=JobStatus.queued,
            queue_name=queue_name,
        )
        self._job_metadata[queue_name][new_job.id] = new_job
        return new_job

    async def get_job_metadata(
        self, job_id: str, queue_name: Optional[str] = None
    ) -> JobMetadata:
        queue_name = self._resolve_queue_name(queue_name)
        try:
            return self._job_metadata[queue_name][job_id]
        except KeyError:
            raise JobNotFound(job_id)

    async def get_job_result(
        self, job_id: str, queue_name: Optional[str] = None
    ) -> JobResult:
        queue_name = self._resolve_queue_name(queue_name)
        try:
            return self._job_results[queue_name][job_id]
        except KeyError:
            raise JobResultUnavailable(job_id)

    async def set_in_progress(
        self, job_id: str, queue_name: Optional[str] = None
    ) -> None:
        """Set a job's status to in progress, for mocking a queue in tests."""
        job = await self.get_job_metadata(job_id, queue_name=queue_name)
        job.status = JobStatus.in_progress

        # An in-progress job cannot have a result
        if job_id in self._job_results:
            del self._job_results[job_id]

    async def set_complete(
        self,
        job_id: str,
        *,
        result: Any,
        success: bool = True,
        queue_name: Optional[str] = None,
    ) -> None:
        """Set a job's result, for mocking a queue in tests."""
        queue_name = self._resolve_queue_name(queue_name)

        job_metadata = await self.get_job_metadata(
            job_id, queue_name=queue_name
        )
        job_metadata.status = JobStatus.complete

        result_info = JobResult(
            id=job_metadata.id,
            name=job_metadata.name,
            args=job_metadata.args,
            kwargs=job_metadata.kwargs,
            status=job_metadata.status,
            enqueue_time=job_metadata.enqueue_time,
            start_time=datetime.now(),
            finish_time=datetime.now(),
            result=result,
            success=success,
            queue_name=queue_name,
        )
        self._job_results[queue_name][job_id] = result_info
