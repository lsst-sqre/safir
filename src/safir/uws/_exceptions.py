"""Exceptions for the Universal Worker Service."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Self, override

from safir.datetime import format_datetime_for_logging
from safir.slack.blockkit import (
    SlackCodeBlock,
    SlackException,
    SlackMessage,
    SlackTextBlock,
    SlackTextField,
    SlackWebException,
)
from safir.slack.sentry import SentryEventInfo
from safir.slack.webhook import SlackIgnoredException

try:
    from vo_models.uws.types import ErrorType

    from safir.arq.uws import WorkerError, WorkerErrorType
except ImportError as e:
    raise ImportError(
        "The safir.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e

from ._models import JobError

__all__ = [
    "DataMissingError",
    "InvalidPhaseError",
    "ParameterError",
    "SyncJobFailedError",
    "SyncJobNoResultsError",
    "SyncJobTimeoutError",
    "TaskError",
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


class TaskError(SlackException):
    """An error occurred during background task processing.

    This exception is constructed based on `~safir.arq.uws.WorkerError`
    exceptions raised by the backend workers. Those exceptions are not used
    directly to avoid making them, and therefore the worker backend code,
    depend on the Slack error reporting code in Safir.

    Attributes
    ----------
    job_id
        UWS job ID, if known.
    started_at
        When the task was started, if known.
    user
        User whose action triggered this exception, for Slack reporting.
    slack_ignore
        Whether to ignore the error for the purposes of Slack reporting.

    Parameters
    ----------
    error_code
        DALI-compatible error code.
    error_type
        Whether the error is transient or permanent.
    message
        Human-readable error message.
    detail
        Additional details about the error.
    cause_type
        Type of the causing exception, if one is available.
    traceback
        Traceback, if one is available.
    slack_ignore
        Whether to ignore the error for the purposes of Slack reporting.
    """

    def __init__(
        self,
        *,
        error_code: str,
        error_type: ErrorType,
        message: str,
        detail: str | None = None,
        cause_type: str | None = None,
        traceback: str | None = None,
        slack_ignore: bool = False,
    ) -> None:
        super().__init__(message)
        self.job_id: str | None = None
        self.slack_ignore = slack_ignore
        self.started_at: datetime | None = None
        self._error_code = error_code
        self._error_type = error_type
        self._message = message
        self._detail = detail
        self._cause_type = cause_type
        self._traceback = traceback

    @classmethod
    def from_worker_error(cls, exc: WorkerError) -> Self:
        """Create an exception based on a backend worker error.

        Parameters
        ----------
        exc
            Backend worker exception.

        Returns
        -------
        TaskError
            Corresponding task exception.
        """
        slack_ignore = False
        match exc.error_type:
            case WorkerErrorType.FATAL:
                error_code = "Error"
                error_type = ErrorType.FATAL
            case WorkerErrorType.TRANSIENT:
                error_code = "ServiceUnavailable"
                error_type = ErrorType.TRANSIENT
            case WorkerErrorType.USAGE:
                error_code = "UsageError"
                error_type = ErrorType.FATAL
                slack_ignore = True
        return cls(
            error_code=error_code,
            error_type=error_type,
            message=str(exc),
            detail=exc.detail,
            cause_type=exc.cause_type,
            traceback=exc.traceback,
            slack_ignore=slack_ignore,
        )

    def to_job_error(self) -> JobError:
        """Convert to a `~safir.uws._models.UWSJobError`."""
        if self._traceback and self._detail:
            detail: str | None = self._detail + "\n\n" + self._traceback
        else:
            detail = self._detail or self._traceback
        return JobError(
            code=self._error_code,
            type=self._error_type,
            message=self._message,
            detail=detail,
        )

    @override
    def to_slack(self) -> SlackMessage:
        message = super().to_slack()
        if self._traceback:
            block = SlackCodeBlock(heading="Traceback", code=self._traceback)
            message.attachments.append(block)
        if self.started_at:
            started_at = format_datetime_for_logging(self.started_at)
            field = SlackTextField(heading="Started at", text=started_at)
            message.fields.insert(1, field)
        if self.job_id:
            field = SlackTextField(heading="UWS job ID", text=self.job_id)
            message.fields.insert(1, field)
        if self._cause_type:
            text = SlackTextBlock(
                heading="Original exception", text=self._cause_type
            )
            message.blocks.append(text)
        if self._detail:
            text = SlackTextBlock(heading="Detail", text=self._detail)
            message.blocks.append(text)
        return message

    @override
    def to_sentry(self) -> SentryEventInfo:
        info = super().to_sentry()
        if self._traceback:
            info.attachments["traceback"] = self._traceback
        if self.started_at:
            started_at = format_datetime_for_logging(self.started_at)
            info.contexts.setdefault("info", {})["started_at"] = started_at
        if self.job_id:
            info.tags["job_id"] = self.job_id
        if self._detail or self._cause_type:
            context = info.contexts.setdefault("original_exception", {})
            if self._detail:
                context["detail"] = self._detail
            if self._cause_type:
                context["cause_type"] = self._cause_type
        return info


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
