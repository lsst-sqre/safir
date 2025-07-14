"""Exceptions for the arq_ client."""

from __future__ import annotations

__all__ = [
    "ArqJobError",
    "JobNotFound",
    "JobNotQueued",
    "JobResultUnavailable",
]


class ArqJobError(Exception):
    """A base class for errors related to arq jobs."""

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
