"""Models for UWS services.

See https://www.ivoa.net/documents/UWS/20161024/REC-UWS-1.1-20161024.html for
most of these models. Descriptive language here is paraphrased from this
standard.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from vo_models.uws import (
    ErrorSummary,
    JobSummary,
    Parameter,
    Parameters,
    ResultReference,
    Results,
    ShortJobDescription,
)
from vo_models.uws.types import ErrorType, ExecutionPhase, UWSVersion

__all__ = [
    "ACTIVE_PHASES",
    "ErrorCode",
    "UWSJob",
    "UWSJobDescription",
    "UWSJobError",
    "UWSJobParameter",
    "UWSJobResult",
    "UWSJobResultSigned",
]


ACTIVE_PHASES = {
    ExecutionPhase.PENDING,
    ExecutionPhase.QUEUED,
    ExecutionPhase.EXECUTING,
}
"""Phases in which the job is active and can be waited on."""


class ErrorCode(StrEnum):
    """Possible error codes in ``text/plain`` responses.

    The following list of errors is taken from the SODA specification and
    therefore may not be appropriate for all DALI services.
    """

    AUTHENTICATION_ERROR = "AuthenticationError"
    AUTHORIZATION_ERROR = "AuthorizationError"
    MULTIVALUED_PARAM_NOT_SUPPORTED = "MultiValuedParamNotSupported"
    ERROR = "Error"
    SERVICE_UNAVAILABLE = "ServiceUnavailable"
    USAGE_ERROR = "UsageError"


@dataclass
class UWSJobError:
    """Failure information about a job."""

    error_type: ErrorType
    """Type of the error."""

    error_code: ErrorCode
    """The SODA error code of this error."""

    message: str
    """Brief error message.

    Note that the UWS specification allows a sequence of messages, but we only
    use a single message and thus a sequence of length one.
    """

    detail: str | None = None
    """Extended error message with additional detail."""

    def to_dict(self) -> dict[str, str | None]:
        """Convert to a dictionary, primarily for logging."""
        return asdict(self)

    def to_xml_model(self) -> ErrorSummary:
        """Convert to a Pydantic XML model."""
        return ErrorSummary(
            message=f"{self.error_code.value}: {self.message}",
            type=self.error_type,
            has_detail=self.detail is not None,
        )


@dataclass
class UWSJobResult:
    """A single result from the job."""

    result_id: str
    """Identifier for the result."""

    url: str
    """The URL for the result, which must point into a GCS bucket."""

    size: int | None = None
    """Size of the result in bytes."""

    mime_type: str | None = None
    """MIME type of the result."""

    def to_xml_model(self) -> ResultReference:
        """Convert to a Pydantic XML model."""
        return ResultReference(
            id=self.result_id, size=self.size, mime_type=self.mime_type
        )


@dataclass
class UWSJobResultSigned:
    """A single result from the job with a signed URL.

    A `UWSJobResult` is converted to a `UWSJobResultSigned` before generating
    the response via templating or returning the URL as a redirect.
    """

    result_id: str
    """Identifier for the result."""

    url: str
    """Signed URL to retrieve the result."""

    size: int | None = None
    """Size of the result in bytes."""

    mime_type: str | None = None
    """MIME type of the result."""

    def to_xml_model(self) -> ResultReference:
        """Convert to a Pydantic XML model."""
        return ResultReference(
            id=self.result_id,
            type=None,
            href=self.url,
            size=self.size,
            mime_type=self.mime_type,
        )


@dataclass
class UWSJobParameter:
    """An input parameter to the job."""

    parameter_id: str
    """Identifier of the parameter."""

    value: str
    """Value of the parameter."""

    def to_dict(self) -> dict[str, str | bool]:
        """Convert to a dictionary, primarily for logging."""
        return asdict(self)

    def to_xml_model(self) -> Parameter:
        """Convert to a Pydantic XML model."""
        return Parameter(id=self.parameter_id, value=self.value)


@dataclass
class UWSJobDescription:
    """Brief job description used for the job list.

    This is a strict subset of the fields of `UWSJob`, but is kept separate
    without an inheritance relationship to reflect how it's used in code.
    """

    job_id: str
    """Unique identifier of the job."""

    message_id: str | None
    """Internal message identifier for the work queuing system."""

    owner: str
    """Identity of the owner of the job."""

    phase: ExecutionPhase
    """Execution phase of the job."""

    run_id: str | None
    """Optional opaque string provided by the client.

    The RunId is intended for the client to add a unique identifier to all
    jobs that are part of a single operation from the perspective of the
    client.  This may aid in tracing issues through a complex system or
    identifying which operation a job is part of.
    """

    creation_time: datetime
    """When the job was created."""

    def to_xml_model(self, base_url: str) -> ShortJobDescription:
        """Convert to a Pydantic XML model.

        Parameters
        ----------
        base_url
            Base URL for the full jobs.
        """
        return ShortJobDescription(
            phase=self.phase,
            run_id=self.run_id,
            creation_time=self.creation_time,
            owner_id=self.owner,
            job_id=self.job_id,
            type=None,
            href=f"{base_url}/{self.job_id}",
        )


class GenericParameters(Parameters):
    """Generic container for UWS job parameters.

    Notes
    -----
    The intended use of `vo_models.uws.Parameters` is to define a subclass
    with the specific parameters valid for that service. However, we store
    parameters as sent to the service as a generic key/value pair in the
    database and define a model that supports arbitrary parsing and
    transformations, so this XML model is both not useful and not clearly
    relevant.

    At least for now, define a generic subclass of `~vo_models.uws.Parameters`
    that holds a generic list of parameters and convert to that for the
    purposes of serialization.
    """

    params: list[Parameter]
    """Job parameters."""


@dataclass
class UWSJob:
    """Represents a single UWS job."""

    job_id: str
    """Unique identifier of the job."""

    message_id: str | None
    """Internal message identifier for the work queuing system."""

    owner: str
    """Identity of the owner of the job."""

    phase: ExecutionPhase
    """Execution phase of the job."""

    run_id: str | None
    """Optional opaque string provided by the client.

    The RunId is intended for the client to add a unique identifier to all
    jobs that are part of a single operation from the perspective of the
    client. This may aid in tracing issues through a complex system or
    identifying which operation a job is part of.
    """

    creation_time: datetime
    """When the job was created."""

    start_time: datetime | None
    """When the job started executing (if it has started)."""

    end_time: datetime | None
    """When the job stopped executing (if it has stopped)."""

    destruction_time: datetime
    """Time at which the job should be destroyed.

    At this time, the job will be aborted if it is still running, its results
    will be deleted, and all record of the job will be discarded.

    This field is optional in the UWS standard, but in this UWS implementation
    all jobs will have a destruction time, so it is not marked as optional.
    """

    execution_duration: timedelta
    """Allowed maximum execution duration in seconds.

    This is specified in elapsed wall clock time, or 0 for unlimited execution
    time. If the job runs for longer than this time period, it will be
    aborted.
    """

    quote: datetime | None
    """Expected completion time of the job if it were started now.

    May be `None` to indicate that the expected duration of the job is not
    known. Maybe later than the destruction time to indicate that the job is
    not possible due to resource constraints.
    """

    error: UWSJobError | None
    """Error information if the job failed."""

    parameters: list[UWSJobParameter]
    """The parameters of the job."""

    results: list[UWSJobResult]
    """The results of the job."""

    def to_xml_model(self) -> JobSummary:
        """Convert to a Pydantic XML model."""
        results = None
        if self.results:
            results = Results(results=[r.to_xml_model() for r in self.results])
        return JobSummary(
            job_id=self.job_id,
            run_id=self.run_id,
            owner_id=self.owner,
            phase=self.phase,
            quote=self.quote,
            creation_time=self.creation_time,
            start_time=self.start_time,
            end_time=self.end_time,
            execution_duration=int(self.execution_duration.total_seconds()),
            destruction=self.destruction_time,
            parameters=GenericParameters(
                params=[p.to_xml_model() for p in self.parameters]
            ),
            results=results,
            error_summary=self.error.to_xml_model() if self.error else None,
            version=UWSVersion.V1_1,
        )
