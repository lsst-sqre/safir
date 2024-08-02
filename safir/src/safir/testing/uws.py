"""Mock UWS job executor for testing."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import TracebackType
from typing import Literal, Self

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from safir.arq import JobMetadata, JobResult, MockArqQueue
from safir.database import create_async_session, create_database_engine
from safir.uws import UWSConfig, UWSJob, UWSJobResult
from safir.uws._service import JobService
from safir.uws._storage import JobStore

__all__ = ["MockUWSJobRunner"]


class MockUWSJobRunner:
    """Simulate execution of jobs with a mock queue.

    When running the test suite, the arq queue is replaced with a mock queue
    that doesn't execute workers. That execution has to be simulated by
    manually updating state in the mock queue and running the UWS database
    worker functions that normally would be run automatically by the queue.

    This class wraps that functionality in an async context manager. An
    instance of it is normally provided as a fixture, initialized with the
    same test objects as the test suite.

    Parameters
    ----------
    config
        UWS configuration.
    arq_queue
        Mock arq queue for testing.
    """

    def __init__(self, config: UWSConfig, arq_queue: MockArqQueue) -> None:
        self._config = config
        self._arq = arq_queue
        self._engine: AsyncEngine
        self._store: JobStore
        self._service: JobService

    async def __aenter__(self) -> Self:
        """Create a database session and the underlying service."""
        # This duplicates some of the code in UWSDependency to avoid needing
        # to set up the result store or to expose UWSFactory outside of the
        # Safir package internals.
        self._engine = create_database_engine(
            self._config.database_url,
            self._config.database_password,
            isolation_level="REPEATABLE READ",
        )
        session = await create_async_session(self._engine)
        self._store = JobStore(session)
        self._service = JobService(
            config=self._config,
            arq_queue=self._arq,
            storage=self._store,
            logger=structlog.get_logger("uws"),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        """Close the database engine and session."""
        await self._engine.dispose()
        return False

    async def get_job_metadata(
        self, username: str, job_id: str
    ) -> JobMetadata:
        """Get the arq job metadata for a job.

        Parameters
        ----------
        job_id
            UWS job ID.

        Returns
        -------
        JobMetadata
            arq job metadata.
        """
        job = await self._service.get(username, job_id)
        assert job.message_id
        return await self._arq.get_job_metadata(job.message_id)

    async def get_job_result(self, username: str, job_id: str) -> JobResult:
        """Get the arq job result for a job.

        Parameters
        ----------
        job_id
            UWS job ID.

        Returns
        -------
        JobMetadata
            arq job metadata.
        """
        job = await self._service.get(username, job_id)
        assert job.message_id
        return await self._arq.get_job_result(job.message_id)

    async def mark_in_progress(
        self, username: str, job_id: str, *, delay: float | None = None
    ) -> UWSJob:
        """Mark a queued job in progress.

        Parameters
        ----------
        username
            Owner of job.
        job_id
            Job ID.
        delay
            How long to delay in seconds before marking the job as complete.

        Returns
        -------
        UWSJob
            Record of the job.
        """
        if delay:
            await asyncio.sleep(delay)
        job = await self._service.get(username, job_id)
        assert job.message_id
        await self._arq.set_in_progress(job.message_id)
        await self._store.mark_executing(job_id, datetime.now(tz=UTC))
        return await self._service.get(username, job_id)

    async def mark_complete(
        self,
        username: str,
        job_id: str,
        results: list[UWSJobResult] | Exception,
        *,
        delay: float | None = None,
    ) -> UWSJob:
        """Mark an in progress job as complete.

        Parameters
        ----------
        username
            Owner of job.
        job_id
            Job ID.
        results
            Results to return. May be an exception to simulate a job failure.
        delay
            How long to delay in seconds before marking the job as complete.

        Returns
        -------
        UWSJob
            Record of the job.
        """
        if delay:
            await asyncio.sleep(delay)
        job = await self._service.get(username, job_id)
        assert job.message_id
        await self._arq.set_complete(job.message_id, result=results)
        job_result = await self._arq.get_job_result(job.message_id)
        await self._store.mark_completed(job_id, job_result)
        return await self._service.get(username, job_id)
