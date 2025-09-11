"""Service layer for a UWS service."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta

from structlog.stdlib import BoundLogger

from safir.datetime import isodatetime

try:
    from vo_models.uws import Jobs, JobSummary
    from vo_models.uws.types import ExecutionPhase
    from vo_models.vosi.availability import Availability

    from safir.arq import ArqQueue, JobMetadata
    from safir.arq.uws import WorkerJobInfo
except ImportError as e:
    raise ImportError(
        "The safir.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e

from ._config import UWSConfig
from ._constants import JOB_STOP_TIMEOUT
from ._exceptions import (
    InvalidPhaseError,
    SyncJobFailedError,
    SyncJobNoResultsError,
    SyncJobTimeoutError,
)
from ._models import (
    ACTIVE_PHASES,
    Job,
    JobError,
    JobResult,
    JobUpdateMetadata,
    ParametersModel,
)
from ._results import ResultStore
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

    async def abort(self, token: str, job_id: str) -> None:
        """Abort a queued or running job.

        If the job is already in a completed state, this operation does
        nothing.

        Parameters
        ----------
        token
            Delegated token for user.
        job_id
            Identifier of the job.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job = await self._storage.get(token, job_id)
        logger = self._build_logger_for_job(job)
        if job.phase not in ACTIVE_PHASES:
            logger.info(f"Cannot stop job in phase {job.phase.value}")
            return
        if job.message_id:
            timeout = JOB_STOP_TIMEOUT.total_seconds()
            logger.info("Aborting queued job", arq_job_id=job.message_id)
            await self._arq.abort_job(job.message_id, timeout=timeout)
        await self._storage.mark_aborted(token, job_id)
        logger.info("Aborted job")

    async def availability(self) -> Availability:
        """Check the availability of underlying services.

        Currently, this does nothing. Eventually, it may do a health check of
        Wobbly.
        """
        return Availability(available=True)

    async def create(
        self,
        token: str,
        parameters: ParametersModel,
        *,
        run_id: str | None = None,
    ) -> Job:
        """Create a pending job.

        This does not start execution of the job. That must be done separately
        with `start`.

        Parameters
        ----------
        token
            Delegated token for user.
        parameters
            The input parameters to the job.
        run_id
            A client-supplied opaque identifier to record with the job.

        Returns
        -------
        Job
            Information about the newly-created job.

        Raises
        ------
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job = await self._storage.create(
            token,
            run_id=run_id,
            parameters=parameters,
            execution_duration=self._config.execution_duration,
            lifetime=self._config.lifetime,
        )
        logger = self._build_logger_for_job(job)
        logger.info("Created job")
        return job

    async def delete(self, token: str, job_id: str) -> None:
        """Delete a job.

        If the job is in an active phase, cancel it before deleting it.

        Parameters
        ----------
        token
            Delegated token for user.
        job_id
            Identifier of job.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job = await self._storage.get(token, job_id)
        logger = self._build_logger_for_job(job)
        if job.phase in ACTIVE_PHASES and job.message_id:
            try:
                await self._arq.abort_job(job.message_id)
            except Exception as e:
                logger.warning("Unable to abort job", error=str(e))
        await self._storage.delete(token, job_id)
        logger.info("Deleted job")

    async def get(
        self,
        token: str,
        job_id: str,
        *,
        wait_seconds: int | None = None,
        wait_phase: ExecutionPhase | None = None,
        wait_for_completion: bool = False,
    ) -> Job:
        """Retrieve a job.

        This also supports long-polling, to implement UWS 1.1 blocking
        behavior, and waiting for completion, to use as a building block when
        constructing a sync API.

        Parameters
        ----------
        token
            Delegated token for user.
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
        Job
            Corresponding job.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.

        Notes
        -----
        ``wait_seconds`` and related parameters are relatively inefficient
        since they poll the database using exponential backoff (starting at a
        0.1s delay and increasing by 1.5x). This may need to be reconsidered
        if it becomes a performance bottleneck.
        """
        job = await self._storage.get(token, job_id)

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
            job = await self._wait_for_job(token, job, until_not, timeout=wait)

        return job

    async def get_error(
        self, token: str, job_id: str
    ) -> list[JobError] | None:
        """Get the errors for a job, if any.

        Parameters
        ----------
        token
            Delegated token for user.
        job_id
            Identifier of the job.

        Returns
        -------
        list of JobError or None
            Error information for the job, or `None` if the job didn't fail.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job = await self._storage.get(token, job_id)
        return job.errors

    async def get_summary(
        self,
        token: str,
        job_id: str,
        *,
        signer: ResultStore | None = None,
        wait_seconds: int | None = None,
        wait_phase: ExecutionPhase | None = None,
    ) -> JobSummary:
        """Retrieve a job's XML model.

        This also supports long-polling, to implement UWS 1.1 blocking
        behavior, and signing of results.

        Parameters
        ----------
        token
            Delegated token for user.
        job_id
            Identifier of the job.
        signer
            If provided, generate signed URLs for the results by using the
            given signing object. If no object is supplied, no URLs will be
            included in the result list.
        wait_seconds
            If given, wait up to this many seconds for the status to change
            before returning. -1 indicates waiting the maximum length of
            time. This is done by polling the database with exponential
            backoff. This will only be honored if the phase is ``PENDING``,
            ``QUEUED``, or ``EXECUTING``.
        wait_phase
            If ``wait`` was given, the starting phase for waiting. Returns
            immediately if the initial phase doesn't match this one.

        Returns
        -------
        JobSummary
            Corresponding job.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.

        Notes
        -----
        ``wait_seconds`` and related parameters are relatively inefficient
        since they poll the database using exponential backoff (starting at a
        0.1s delay and increasing by 1.5x). This may need to be reconsidered
        if it becomes a performance bottleneck.
        """
        job = await self.get(
            token, job_id, wait_seconds=wait_seconds, wait_phase=wait_phase
        )
        if signer:
            job.results = [signer.sign_url(r) for r in job.results]
        return job.to_xml_model(self._config.job_summary_type)

    async def list_jobs(
        self,
        token: str,
        base_url: str,
        *,
        phases: list[ExecutionPhase] | None = None,
        after: datetime | None = None,
        count: int | None = None,
    ) -> Jobs:
        """List the jobs for a particular user.

        Parameters
        ----------
        token
            Delegated token for user.
        base_url
            Base URL used to form URLs to the specific jobs.
        phases
            Limit the result to jobs in this list of possible execution
            phases.
        after
            Limit the result to jobs created after the given datetime.
        count
            Limit the results to the most recent count jobs.

        Returns
        -------
        Jobs
            Collection of short job descriptions.

        Raises
        ------
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        jobs = await self._storage.list_jobs(
            token, phases=phases, after=after, count=count
        )
        return Jobs(jobref=[j.to_job_description(base_url) for j in jobs])

    async def run_sync(
        self,
        token: str,
        user: str,
        parameters: ParametersModel,
        *,
        runid: str | None,
    ) -> JobResult:
        """Create a job for a sync request and return the first result.

        Parameters
        ----------
        token
            Delegated token for user.
        user
            User on behalf of whom this operation is performed.
        params
            Job parameters.
        user
            Username of user running the job.
        runid
            User-supplied RunID, if any.

        Returns
        -------
        JobResult
            First result of the successfully-executed job.

        Raises
        ------
        SyncJobFailedError
            Raised if the job failed.
        SyncJobNoResultsError
            Raised if the job returned no results.
        SyncJobTimeoutError
            Raised if the job execution timed out.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job = await self.create(token, parameters, run_id=runid)
        logger = self._build_logger_for_job(job)

        # Start the job and wait for it to complete.
        metadata = await self.start(token, user, job.id)
        logger = logger.bind(arq_job_id=metadata.id)
        job = await self.get(
            token,
            job.id,
            wait_seconds=int(self._config.sync_timeout.total_seconds()),
            wait_for_completion=True,
        )

        # Check for error states.
        if job.phase not in (ExecutionPhase.COMPLETED, ExecutionPhase.ERROR):
            logger.warning("Job timed out", timeout=self._config.sync_timeout)
            raise SyncJobTimeoutError(self._config.sync_timeout)
        if job.errors:
            # Only one error is supported for right now.
            error = job.errors[0]
            logger.warning("Job failed", error=error.model_dump(mode="json"))
            raise SyncJobFailedError(error)
        if not job.results:
            logger.warning("Job returned no results")
            raise SyncJobNoResultsError

        # Return the first result.
        return job.results[0]

    async def start(self, token: str, user: str, job_id: str) -> JobMetadata:
        """Start execution of a job.

        Parameters
        ----------
        token
            Gafaelfawr token used to authenticate to services used by the
            backend on the user's behalf.
        user
            User on behalf of whom this operation is performed.
        job_id
            Identifier of the job to start.

        Returns
        -------
        JobMetadata
            arq job metadata.

        Raises
        ------
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job = await self._storage.get(token, job_id)
        if job.phase not in (ExecutionPhase.PENDING, ExecutionPhase.HELD):
            raise InvalidPhaseError(f"Cannot start job in phase {job.phase}")
        logger = self._build_logger_for_job(job)
        info = WorkerJobInfo(
            job_id=job.id,
            user=user,
            token=token,
            timeout=job.execution_duration or self._config.lifetime,
            run_id=job.run_id,
        )
        params = job.parameters.to_worker_parameters().model_dump(mode="json")
        metadata = await self._arq.enqueue(self._config.worker, params, info)
        await self._storage.mark_queued(token, job_id, metadata)
        logger.info("Started job", arq_job_id=metadata.id)
        return metadata

    async def update_destruction(
        self, token: str, job_id: str, destruction: datetime
    ) -> datetime | None:
        """Update the destruction time of a job.

        Parameters
        ----------
        token
            Delegated token for user.
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
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job = await self._storage.get(token, job_id)
        logger = self._build_logger_for_job(job)

        # Validate the new value.
        if validator := self._config.validate_destruction:
            destruction = validator(destruction, job)
        elif destruction > job.destruction_time:
            destruction = job.destruction_time

        # Update the destruction time if needed.
        if destruction == job.destruction_time:
            return None
        metadata = JobUpdateMetadata(
            destruction_time=destruction,
            execution_duration=job.execution_duration,
        )
        await self._storage.update_metadata(token, job_id, metadata)
        logger.info(
            "Changed job destruction time",
            destruction=isodatetime(destruction),
        )
        return destruction

    async def update_execution_duration(
        self, token: str, job_id: str, duration: timedelta | None
    ) -> timedelta | None:
        """Update the execution duration time of a job.

        Parameters
        ----------
        token
            Delegated token for user.
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
        UnknownJobError
            Raised if the job was not found.
        WobblyError
            Raised if the Wobbly request fails or returns a failure status.
        """
        job = await self._storage.get(token, job_id)
        logger = self._build_logger_for_job(job)

        # Validate the new value.
        if validator := self._config.validate_execution_duration:
            duration = validator(duration, job)
        if duration:
            duration = min(duration, self._config.execution_duration)

        # Update the duration in the job.
        if duration == job.execution_duration:
            return None
        update = JobUpdateMetadata(
            destruction_time=job.destruction_time, execution_duration=duration
        )
        await self._storage.update_metadata(token, job_id, update)
        if duration:
            duration_str = f"{duration.total_seconds()}s"
        else:
            duration_str = "unlimited"
        logger.info("Changed job execution duration", duration=duration_str)
        return duration

    def _build_logger_for_job(self, job: Job) -> BoundLogger:
        """Construct a logger with bound information for a job.

        Parameters
        ----------
        job
            Job for which to report messages.

        Returns
        -------
        BoundLogger
            Logger with more bound metadata.
        """
        logger = self._logger.bind(user=job.owner, job_id=job.id)
        if job.run_id:
            logger = logger.bind(run_id=job.run_id)
        if job.parameters:
            parameters = job.parameters.model_dump(mode="json")
            logger = logger.bind(parameters=parameters)
        return logger

    async def _wait_for_job(
        self,
        token: str,
        job: Job,
        until_not: set[ExecutionPhase],
        *,
        timeout: timedelta,
    ) -> Job:
        """Wait for the completion of a job.

        Parameters
        ----------
        token
            Delegated token for user.
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
                    job = await self._storage.get(token, job.id)
                    delay = min(delay * 1.5, max_delay)

        # If we timed out, we may have done so in the middle of a delay. Try
        # one last request.
        return await self._storage.get(token, job.id)
