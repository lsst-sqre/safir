"""Service layer for a UWS service."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta

from structlog.stdlib import BoundLogger
from vo_models.uws.types import ExecutionPhase
from vo_models.vosi.availability import Availability

from safir.arq import ArqQueue, JobMetadata
from safir.arq.uws import WorkerJobInfo
from safir.datetime import isodatetime

from ._config import ParametersModel, UWSConfig
from ._constants import JOB_STOP_TIMEOUT
from ._exceptions import (
    InvalidPhaseError,
    PermissionDeniedError,
    SyncJobFailedError,
    SyncJobNoResultsError,
    SyncJobTimeoutError,
)
from ._models import (
    ACTIVE_PHASES,
    UWSJob,
    UWSJobDescription,
    UWSJobParameter,
    UWSJobResult,
)
from ._storage import JobStore

__all__ = ["JobService"]


class JobService:
    """Dispatch and track UWS jobs.

    The goal of this layer is to encapsulate the machinery of a service that
    dispatches jobs using arq, without making assumptions about what the jobs
    do or what outputs they may return. Workers mostly do not use this layer
    and instead talk directly to the `~safir.uws._storage.WorkerJobStore`.

    Parameters
    ----------
    config
        UWS configuration.
    arq_queue
        arq queue to which to dispatch jobs.
    storage
        Underlying storage for job metadata and result tracking.
    logger
        Logger to use.
    """

    def __init__(
        self,
        *,
        config: UWSConfig,
        arq_queue: ArqQueue,
        storage: JobStore,
        logger: BoundLogger,
    ) -> None:
        self._config = config
        self._arq = arq_queue
        self._storage = storage
        self._logger = logger

    async def abort(self, user: str, job_id: str) -> None:
        """Abort a queued or running job.

        If the job is already in a completed state, this operation does
        nothing.

        Parameters
        ----------
        user
            User on behalf of whom this operation is performed.
        job_id
            Identifier of the job.

        Raises
        ------
        PermissionDeniedError
            If the job ID doesn't exist or is for a user other than the
            provided user.
        """
        job = await self._storage.get(job_id)
        if job.owner != user:
            raise PermissionDeniedError(f"Access to job {job_id} denied")
        params_model = self._validate_parameters(job.parameters)
        logger = self._build_logger_for_job(job, params_model)
        if job.phase not in ACTIVE_PHASES:
            logger.info(f"Cannot stop job in phase {job.phase.value}")
            return
        if job.message_id:
            timeout = JOB_STOP_TIMEOUT.total_seconds()
            logger.info("Aborting queued job", arq_job_id=job.message_id)
            await self._arq.abort_job(job.message_id, timeout=timeout)
        await self._storage.mark_aborted(job_id)
        logger.info("Aborted job")

    async def availability(self) -> Availability:
        """Check whether the service is up.

        Used for ``/availability`` endpoints. Currently this only checks the
        database.

        Returns
        -------
        Availability
            Service availability information.
        """
        return await self._storage.availability()

    async def create(
        self,
        user: str,
        params: list[UWSJobParameter],
        *,
        run_id: str | None = None,
    ) -> UWSJob:
        """Create a pending job.

        This does not start execution of the job. That must be done separately
        with `start`.

        Parameters
        ----------
        user
            User on behalf this operation is performed.
        run_id
            A client-supplied opaque identifier to record with the job.
        params
            The input parameters to the job.

        Returns
        -------
        safir.uws._models.Job
            The internal representation of the newly-created job.
        """
        params_model = self._validate_parameters(params)
        job = await self._storage.add(
            owner=user,
            run_id=run_id,
            params=params,
            execution_duration=self._config.execution_duration,
            lifetime=self._config.lifetime,
        )
        logger = self._build_logger_for_job(job, params_model)
        logger.info("Created job")
        return job

    async def delete(self, user: str, job_id: str) -> None:
        """Delete a job.

        If the job is in an active phase, cancel it before deleting it.

        Parameters
        ----------
        user
            Owner of job.
        job_id
            Identifier of job.
        """
        job = await self._storage.get(job_id)
        if job.owner != user:
            raise PermissionDeniedError(f"Access to job {job_id} denied")
        logger = self._logger.bind(user=user, job_id=job_id)
        if job.phase in ACTIVE_PHASES and job.message_id:
            try:
                await self._arq.abort_job(job.message_id)
            except Exception as e:
                logger.warning("Unable to abort job", error=str(e))
        await self._storage.delete(job_id)
        logger.info("Deleted job")

    async def delete_expired(self) -> None:
        """Delete all expired jobs.

        A job is expired if it has passed its destruction time. If the job is
        in an active phase, cancel it before deleting it.
        """
        jobs = await self._storage.list_expired()
        if jobs:
            self._logger.info(f"Deleting {len(jobs)} expired jobs")
        for job in jobs:
            if job.phase in ACTIVE_PHASES and job.message_id:
                try:
                    await self._arq.abort_job(job.message_id)
                except Exception as e:
                    self._logger.warning(
                        "Unable to abort expired job", error=str(e)
                    )
            await self._storage.delete(job.job_id)
            self._logger.info("Deleted expired job")
        self._logger.info(f"Finished deleting {len(jobs)} expired jobs")

    async def get(
        self,
        user: str,
        job_id: str,
        *,
        wait_seconds: int | None = None,
        wait_phase: ExecutionPhase | None = None,
        wait_for_completion: bool = False,
    ) -> UWSJob:
        """Retrieve a job.

        This also supports long-polling, to implement UWS 1.1 blocking
        behavior, and waiting for completion, to use as a building block when
        constructing a sync API.

        Parameters
        ----------
        user
            User on behalf this operation is performed.
        job_id
            Identifier of the job.
        wait_seconds
            If given, wait up to this many seconds for the status to change
            before returning. -1 indicates waiting the maximum length of
            time. This is done by polling the database with exponential
            backoff. This will only be honored if the phase is ``PENDING``,
            ``QUEUED``, or ``EXECUTING``.
        wait_phase
            If ``wait`` was given, the starting phase for waiting. Returns
            immediately if the initial phase doesn't match this one.
        wait_for_completion
            If set to true, wait until the job completes (has a phase other
            than ``QUEUED`` or ``EXECUTING``). Only one of this or
            ``wait_phase`` should be given. Ignored if ``wait`` was not given.

        Returns
        -------
        UWSJob
            The corresponding job.

        Raises
        ------
        PermissionDeniedError
            If the job ID doesn't exist or is for a user other than the
            provided user.

        Notes
        -----
        ``wait`` and related parameters are relatively inefficient since they
        poll the database using exponential backoff (starting at a 0.1s delay
        and increasing by 1.5x). This may need to be reconsidered if it
        becomes a performance bottleneck.
        """
        job = await self._storage.get(job_id)
        if job.owner != user:
            raise PermissionDeniedError(f"Access to job {job_id} denied")

        # If waiting for a status change was requested and is meaningful, do
        # so, capping the wait time at the configured maximum timeout.
        if wait_seconds and job.phase in ACTIVE_PHASES:
            if wait_seconds < 0:
                wait = self._config.wait_timeout
            else:
                wait = timedelta(seconds=wait_seconds)
                wait = min(wait, self._config.wait_timeout)
            if wait_for_completion:
                until_not = ACTIVE_PHASES
            else:
                until_not = {wait_phase} if wait_phase else {job.phase}
            job = await self._wait_for_job(job, until_not, wait)

        return job

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
            Limit the result to jobs created after the given datetime.
        count
            Limit the results to the most recent count jobs.

        Returns
        -------
        list of safir.uws._models.JobDescription
            List of job descriptions matching the search criteria.
        """
        return await self._storage.list_jobs(
            user, phases=phases, after=after, count=count
        )

    async def run_sync(
        self,
        user: str,
        params: list[UWSJobParameter],
        *,
        token: str,
        runid: str | None,
    ) -> UWSJobResult:
        """Create a job for a sync request and return the first result.

        Parameters
        ----------
        params
            Job parameters.
        user
            Username of user running the job.
        token
            Delegated Gafaelfawr token to pass to the backend worker.
        runid
            User-supplied RunID, if any.

        Returns
        -------
        result
            First result of the successfully-executed job.

        Raises
        ------
        SyncJobFailedError
            Raised if the job failed.
        SyncJobNoResultsError
            Raised if the job returned no results.
        SyncJobTimeoutError
            Raised if the job execution timed out.
        """
        job = await self.create(user, params, run_id=runid)
        params_model = self._validate_parameters(params)
        logger = self._build_logger_for_job(job, params_model)

        # Start the job and wait for it to complete.
        metadata = await self.start(user, job.job_id, token)
        logger = logger.bind(arq_job_id=metadata.id)
        job = await self.get(
            user,
            job.job_id,
            wait_seconds=int(self._config.sync_timeout.total_seconds()),
            wait_for_completion=True,
        )

        # Check for error states.
        if job.phase not in (ExecutionPhase.COMPLETED, ExecutionPhase.ERROR):
            logger.warning("Job timed out", timeout=self._config.sync_timeout)
            raise SyncJobTimeoutError(self._config.sync_timeout)
        if job.error:
            logger.warning("Job failed", error=job.error.to_dict())
            raise SyncJobFailedError(job.error)
        if not job.results:
            logger.warning("Job returned no results")
            raise SyncJobNoResultsError

        # Return the first result.
        return job.results[0]

    async def start(self, user: str, job_id: str, token: str) -> JobMetadata:
        """Start execution of a job.

        Parameters
        ----------
        user
            User on behalf of whom this operation is performed.
        job_id
            Identifier of the job to start.
        token
            Gafaelfawr token used to authenticate to services used by the
            backend on the user's behalf.

        Returns
        -------
        JobMetadata
            arq job metadata.

        Raises
        ------
        safir.uws._exceptions.PermissionDeniedError
            If the job ID doesn't exist or is for a user other than the
            provided user.
        """
        job = await self._storage.get(job_id)
        if job.owner != user:
            raise PermissionDeniedError(f"Access to job {job_id} denied")
        if job.phase not in (ExecutionPhase.PENDING, ExecutionPhase.HELD):
            raise InvalidPhaseError("Cannot start job in phase {job.phase}")
        params_model = self._validate_parameters(job.parameters)
        logger = self._build_logger_for_job(job, params_model)
        info = WorkerJobInfo(
            job_id=job.job_id,
            user=user,
            token=token,
            timeout=job.execution_duration,
            run_id=job.run_id,
        )
        params = params_model.to_worker_parameters().model_dump(mode="json")
        metadata = await self._arq.enqueue(self._config.worker, params, info)
        await self._storage.mark_queued(job_id, metadata)
        logger.info("Started job", arq_job_id=metadata.id)
        return metadata

    async def update_destruction(
        self, user: str, job_id: str, destruction: datetime
    ) -> datetime | None:
        """Update the destruction time of a job.

        Parameters
        ----------
        user
            User on behalf of whom this operation is performed
        job_id
            Identifier of the job to update.
        destruction
            The new job destruction time. This may be modified by the service
            callback if it so desires.

        Returns
        -------
        datetime.datetime or None
            The new destruction time of the job (possibly modified by the
            callback), or `None` if the destruction time of the job was
            not changed.

        Raises
        ------
        safir.uws._exceptions.PermissionDeniedError
            If the job ID doesn't exist or is for a user other than the
            provided user.
        """
        job = await self._storage.get(job_id)
        if job.owner != user:
            raise PermissionDeniedError(f"Access to job {job_id} denied")

        # Validate the new value.
        if validator := self._config.validate_destruction:
            destruction = validator(destruction, job)
        elif destruction > job.destruction_time:
            destruction = job.destruction_time

        # Update the destruction time if needed.
        if destruction == job.destruction_time:
            return None
        await self._storage.update_destruction(job_id, destruction)
        self._logger.info(
            "Changed job destruction time",
            user=user,
            job_id=job_id,
            destruction=isodatetime(destruction),
        )
        return destruction

    async def update_execution_duration(
        self, user: str, job_id: str, duration: timedelta
    ) -> timedelta | None:
        """Update the execution duration time of a job.

        Parameters
        ----------
        user
            User on behalf of whom this operation is performed
        job_id
            Identifier of the job to update.
        duration
            The new job execution duration. This may be modified by the service
            callback if it so desires.

        Returns
        -------
        timedelta or None
            The new execution duration of the job (possibly modified by the
            callback), or `None` if the execution duration of the job was
            not changed.

        Raises
        ------
        safir.uws._exceptions.PermissionDeniedError
            If the job ID doesn't exist or is for a user other than the
            provided user.
        """
        job = await self._storage.get(job_id)
        if job.owner != user:
            raise PermissionDeniedError(f"Access to job {job_id} denied")

        # Validate the new value.
        if validator := self._config.validate_execution_duration:
            duration = validator(duration, job)
        duration = min(duration, self._config.execution_duration)

        # Update the duration in the job.
        if duration == job.execution_duration:
            return None
        await self._storage.update_execution_duration(job_id, duration)
        if duration.total_seconds() > 0:
            duration_str = f"{duration.total_seconds()}s"
        else:
            duration_str = "unlimited"
        self._logger.info(
            "Changed job execution duration",
            user=user,
            job_id=job_id,
            duration=duration_str,
        )
        return duration

    def _build_logger_for_job(
        self, job: UWSJob, params: ParametersModel | None
    ) -> BoundLogger:
        """Construct a logger with bound information for a job.

        Parameters
        ----------
        job
            Job for which to report messages.
        params
            Job parameters in model form, if available.

        Returns
        -------
        BoundLogger
            Logger with more bound metadata.
        """
        logger = self._logger.bind(user=job.owner, job_id=job.job_id)
        if job.run_id:
            logger = logger.bind(run_id=job.run_id)
        if params:
            logger = logger.bind(parameters=params.model_dump(mode="json"))
        return logger

    def _validate_parameters(
        self, params: list[UWSJobParameter]
    ) -> ParametersModel:
        """Convert UWS job parameters to the parameter model for the service.

        As a side effect, this also verifies that the parameters are valid,
        so it is used when creating a job or modifying its parameters to
        ensure that the new parameters are valid.

        Parameters
        ----------
        params
            Job parameters in the UWS job parameter format.

        Returns
        -------
        pydantic.BaseModel
            Paramters in the model provided by the service, which will be
            some subclass of `pydantic.BaseModel`.

        Raises
        ------
        safir.uws.UWSError
            Raised if there is some problem with the job parameters.
        """
        return self._config.parameters_type.from_job_parameters(params)

    async def _wait_for_job(
        self, job: UWSJob, until_not: set[ExecutionPhase], timeout: timedelta
    ) -> UWSJob:
        """Wait for the completion of a job.

        Parameters
        ----------
        job
            Job to wait for.
        until_not
            Wait until the job is no longer in one of this set of phases.
        timeout
            How long to wait.

        Returns
        -------
        Job
            The new state of the job.
        """
        # I don't know of a way to set a watch on the database, so use
        # polling. Poll the database with exponential delay starting with 0.1
        # seconds and increasing by 1.5x each time until we reach the maximum
        # duration.
        delay = 0.1
        max_delay = 5
        with suppress(TimeoutError):
            async with asyncio.timeout(timeout.total_seconds()):
                while job.phase in until_not:
                    await asyncio.sleep(delay)
                    job = await self._storage.get(job.job_id)
                    delay = min(delay * 1.5, max_delay)

        # If we timed out, we may have done so in the middle of a delay. Try
        # one last request.
        return await self._storage.get(job.job_id)
