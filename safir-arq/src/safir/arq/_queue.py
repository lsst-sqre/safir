"""An arq_ client with a mock for testing."""

from __future__ import annotations

import abc
import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, Self, override

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.constants import default_queue_name as arq_default_queue_name
from arq.jobs import Job, JobStatus

from ._exceptions import JobNotFound, JobNotQueued, JobResultUnavailable
from ._models import JobMetadata, JobResult

__all__ = [
    "ArqQueue",
    "MockArqQueue",
    "RedisArqQueue",
]


class ArqQueue(metaclass=abc.ABCMeta):
    """A common interface for working with an arq queue that can be
    implemented either with a real Redis backend, or an in-memory repository
    for testing.

    See Also
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
        """Name of the default queue, if the ``_queue_name`` parameter is not
        set in method calls.
        """
        return self._default_queue_name

    @abc.abstractmethod
    async def enqueue(
        self,
        task_name: str,
        *task_args: Any,
        _queue_name: str | None = None,
        **task_kwargs: Any,
    ) -> JobMetadata:
        """Add a job to the queue.

        Parameters
        ----------
        task_name
            The function name to run.
        *task_args
            Positional arguments for the task function.
        _queue_name
            Name of the queue.
        **task_kwargs
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
    async def abort_job(
        self,
        job_id: str,
        queue_name: str | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Abort a queued or running job.

        The worker must be configured to allow aborting jobs for this to
        succeed.

        Parameters
        ----------
        job_id
            The job's identifier.
        queue_name
            Name of the queue.
        timeout
            How long to wait for the job result before raising `TimeoutError`.
            If `None`, waits forever.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_job_metadata(
        self, job_id: str, queue_name: str | None = None
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
        self, job_id: str, queue_name: str | None = None
    ) -> JobResult:
        """Retrieve the job result, if available.

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
        return cls(pool, default_queue_name=default_queue_name)

    @override
    async def enqueue(
        self,
        task_name: str,
        *task_args: Any,
        _queue_name: str | None = None,
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
            # TODO(jonathansick): if implementing hard-coded job IDs, set as
            # an argument
            raise JobNotQueued(None)

    def _get_job(self, job_id: str, queue_name: str | None = None) -> Job:
        return Job(
            job_id,
            self._pool,
            _queue_name=queue_name or self.default_queue_name,
        )

    @override
    async def abort_job(
        self,
        job_id: str,
        queue_name: str | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        job = self._get_job(job_id, queue_name=queue_name)
        return await job.abort(timeout=timeout)

    @override
    async def get_job_metadata(
        self, job_id: str, queue_name: str | None = None
    ) -> JobMetadata:
        job = self._get_job(job_id, queue_name=queue_name)
        return await JobMetadata.from_job(job)

    @override
    async def get_job_result(
        self, job_id: str, queue_name: str | None = None
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

    @override
    async def enqueue(
        self,
        task_name: str,
        *task_args: Any,
        _queue_name: str | None = None,
        **task_kwargs: Any,
    ) -> JobMetadata:
        queue_name = self._resolve_queue_name(_queue_name)
        new_job = JobMetadata(
            id=str(uuid.uuid4().hex),
            name=task_name,
            args=task_args,
            kwargs=task_kwargs,
            enqueue_time=datetime.now(tz=UTC),
            status=JobStatus.queued,
            queue_name=queue_name,
        )
        self._job_metadata[queue_name][new_job.id] = new_job
        return new_job

    @override
    async def abort_job(
        self,
        job_id: str,
        queue_name: str | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        queue_name = self._resolve_queue_name(queue_name)
        try:
            job_metadata = self._job_metadata[queue_name][job_id]
        except KeyError:
            return False

        # If the job was started, simulate cancelling it.
        if job_metadata.status == JobStatus.in_progress:
            job_metadata.status = JobStatus.complete
            result_info = JobResult(
                id=job_metadata.id,
                name=job_metadata.name,
                args=job_metadata.args,
                kwargs=job_metadata.kwargs,
                status=job_metadata.status,
                enqueue_time=job_metadata.enqueue_time,
                start_time=datetime.now(tz=UTC),
                finish_time=datetime.now(tz=UTC),
                result=asyncio.CancelledError(),
                success=False,
                queue_name=queue_name,
            )
            self._job_results[queue_name][job_id] = result_info
            return True

        # If it was just queued, delete it.
        if job_metadata.status in (JobStatus.deferred, JobStatus.queued):
            del self._job_metadata[queue_name][job_id]
            return True

        # Otherwise, the job has already completed, so we can't abort it.
        return False

    @override
    async def get_job_metadata(
        self, job_id: str, queue_name: str | None = None
    ) -> JobMetadata:
        queue_name = self._resolve_queue_name(queue_name)
        try:
            return self._job_metadata[queue_name][job_id]
        except KeyError as e:
            raise JobNotFound(job_id) from e

    @override
    async def get_job_result(
        self, job_id: str, queue_name: str | None = None
    ) -> JobResult:
        queue_name = self._resolve_queue_name(queue_name)
        try:
            return self._job_results[queue_name][job_id]
        except KeyError as e:
            raise JobResultUnavailable(job_id) from e

    async def set_in_progress(
        self, job_id: str, queue_name: str | None = None
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
        queue_name: str | None = None,
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
            start_time=datetime.now(tz=UTC),
            finish_time=datetime.now(tz=UTC),
            result=result,
            success=success,
            queue_name=queue_name,
        )
        self._job_results[queue_name][job_id] = result_info
