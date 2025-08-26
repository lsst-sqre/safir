"""Exceptions for the Universal Worker Service."""

from __future__ import annotations

from datetime import timedelta

from safir.slack.blockkit import SlackWebException
from safir.slack.webhook import SlackIgnoredException

from ._models import JobError

__all__ = [
    "DataMissingError",
    "InvalidPhaseError",
    "ParameterError",
    "SyncJobFailedError",
    "SyncJobNoResultsError",
    "SyncJobTimeoutError",
    "UWSError",
    "UnknownJobError",
    "UsageError",
    "WobblyError",
]


class UWSError(SlackIgnoredException):
    """An error with an associated error code.

    SODA requires errors be in ``text/plain`` and start with an error code.
    Adopt that as a general representation of errors produced by the UWS
    layer to simplify generating error responses.

    Parameters
    ----------
    error_code
        SODA error code.
    message
        Exception message, which will be the stringification of the exception.
    detail
        Additional detail.
    """

    def __init__(
        self, error_code: str, message: str, detail: str | None = None
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.detail = detail
        self.status_code = 400


class SyncJobFailedError(UWSError):
    """A sync job failed."""

    def __init__(self, error: JobError) -> None:
        super().__init__(error.code, error.message, error.detail)
        self.status_code = 500


class SyncJobNoResultsError(UWSError):
    """A sync job returned no results."""

    def __init__(self) -> None:
        msg = "Job completed but produced no results"
        super().__init__("Error", msg)
        self.status_code = 500


class SyncJobTimeoutError(UWSError):
    """A sync job timed out before it completed."""

    def __init__(self, timeout: timedelta) -> None:
        msg = f"Job did not complete in {timeout.total_seconds()}s"
        super().__init__("Error", msg)
        self.status_code = 500


class UsageError(UWSError):
    """Invalid parameters were passed to a UWS API."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__("UsageError", message, detail)
        self.status_code = 422


class DataMissingError(UWSError):
    """The data requested does not exist for that job."""

    def __init__(self, message: str) -> None:
        super().__init__("UsageError", message)
        self.status_code = 404


class InvalidPhaseError(UsageError):
    """The job is in an invalid phase for the desired operation."""


class ParameterError(UsageError):
    """Unsupported value passed to a parameter."""


class UnknownJobError(DataMissingError):
    """The named job could not be found in the database."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id} not found")
        self.job_id = job_id


class WobblyError(SlackWebException):
    """An error occurred making a request to Wobbly."""
