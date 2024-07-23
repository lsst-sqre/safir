"""Support functions for testing UWS code."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated, Self

from arq.connections import RedisSettings
from fastapi import Form, Query
from pydantic import BaseModel, SecretStr

from safir.arq import ArqMode, JobMetadata, JobResult, MockArqQueue
from safir.uws import (
    ParametersModel,
    UWSConfig,
    UWSJob,
    UWSJobParameter,
    UWSJobResult,
    UWSRoute,
)
from safir.uws._dependencies import UWSFactory

__all__ = [
    "MockJobRunner",
    "SimpleParameters",
    "build_uws_config",
]


class SimpleWorkerParameters(BaseModel):
    name: str


class SimpleParameters(ParametersModel[SimpleWorkerParameters]):
    name: str

    @classmethod
    def from_job_parameters(cls, params: list[UWSJobParameter]) -> Self:
        assert len(params) == 1
        assert params[0].parameter_id == "name"
        return cls(name=params[0].value)

    def to_worker_parameters(self) -> SimpleWorkerParameters:
        return SimpleWorkerParameters(name=self.name)


async def _get_dependency(
    name: Annotated[str, Query()],
) -> list[UWSJobParameter]:
    return [UWSJobParameter(parameter_id="name", value=name)]


async def _post_dependency(
    name: Annotated[str, Form()],
) -> list[UWSJobParameter]:
    return [UWSJobParameter(parameter_id="name", value=name)]


def build_uws_config(database_url: str, database_password: str) -> UWSConfig:
    """Set up a test configuration."""
    return UWSConfig(
        arq_mode=ArqMode.test,
        arq_redis_settings=RedisSettings(host="localhost", port=6379),
        async_post_route=UWSRoute(
            dependency=_post_dependency, summary="Create async job"
        ),
        database_url=database_url,
        database_password=SecretStr(database_password),
        execution_duration=timedelta(minutes=10),
        lifetime=timedelta(days=1),
        parameters_type=SimpleParameters,
        signing_service_account="signer@example.com",
        slack_webhook=SecretStr("https://example.com/fake-webhook"),
        sync_get_route=UWSRoute(
            dependency=_get_dependency, summary="Sync request"
        ),
        sync_post_route=UWSRoute(
            dependency=_post_dependency, summary="Sync request"
        ),
        worker="hello",
    )


class MockJobRunner:
    """Simulate execution of jobs with a mock queue.

    When running the test suite, the arq queue is replaced with a mock queue
    that doesn't execute workers. That execution has to be simulated by
    manually updating state in the mock queue and running the UWS database
    worker functions that normally would be run automatically by the queue.

    This class wraps that functionality. An instance of it is normally
    provided as a fixture, initialized with the same test objects as the test
    suite.

    Parameters
    ----------
    factory
        Factory for UWS components.
    arq_queue
        Mock arq queue for testing.
    """

    def __init__(self, factory: UWSFactory, arq_queue: MockArqQueue) -> None:
        self._service = factory.create_job_service()
        self._store = factory.create_job_store()
        self._arq = arq_queue

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
