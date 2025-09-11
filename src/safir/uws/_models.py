"""Models for UWS services.

See https://www.ivoa.net/documents/UWS/20161024/REC-UWS-1.1-20161024.html for
most of these models. Descriptive language here is paraphrased from this
standard.
"""

from abc import ABC, abstractmethod
from typing import Annotated, Any, Literal, Self, override

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer

from safir.pydantic import SecondsTimedelta, UtcDatetime

try:
    from vo_models.uws import (
        ErrorSummary,
        JobSummary,
        Parameters,
        ResultReference,
        Results,
        ShortJobDescription,
    )
    from vo_models.uws.types import ErrorType, ExecutionPhase, UWSVersion

    from safir.arq.uws import WorkerResult
except ImportError as e:
    raise ImportError(
        "The safir.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e

__all__ = [
    "ACTIVE_PHASES",
    "Job",
    "JobCreate",
    "JobError",
    "JobResult",
    "JobUpdateAborted",
    "JobUpdateCompleted",
    "JobUpdateError",
    "JobUpdateExecuting",
    "JobUpdateMetadata",
    "JobUpdateQueued",
    "ParametersModel",
    "SignedJobResult",
]


ACTIVE_PHASES = {
    ExecutionPhase.PENDING,
    ExecutionPhase.QUEUED,
    ExecutionPhase.EXECUTING,
}
"""Phases in which the job is active and can be waited on."""


class ParametersModel[W: BaseModel, X: Parameters](BaseModel, ABC):
    """Defines the interface for a model suitable for job parameters."""

    @abstractmethod
    def to_worker_parameters(self) -> W:
        """Convert to the domain model used by the backend worker."""

    @abstractmethod
    def to_xml_model(self) -> X:
        """Convert to the XML model used in XML API responses."""


class JobError(BaseModel):
    """Failure information about a job."""

    type: Annotated[
        ErrorType,
        Field(
            title="Error type",
            description="Type of the error",
            examples=[ErrorType.TRANSIENT, ErrorType.FATAL],
        ),
    ]

    code: Annotated[
        str,
        Field(
            title="Error code",
            description="Code for this class of error",
            examples=["ServiceUnavailable"],
        ),
    ]

    message: Annotated[
        str,
        Field(
            title="Error message",
            description="Brief error messages",
            examples=["Short error message"],
        ),
    ]

    detail: Annotated[
        str | None,
        Field(
            title="Extended error message",
            description="Extended error message with additional detail",
            examples=["Some longer error message with details", None],
        ),
    ] = None

    def to_xml_model(self) -> ErrorSummary:
        """Convert to a Pydantic XML model."""
        return ErrorSummary(
            message=f"{self.code}: {self.message}",
            type=self.type,
            has_detail=self.detail is not None,
        )


class JobResult(BaseModel):
    """A single result from a job."""

    id: Annotated[
        str,
        Field(
            title="Result ID",
            description="Identifier for this result",
            examples=["image", "metadata"],
        ),
    ]

    url: Annotated[
        str,
        Field(
            title="Result URL",
            description="URL where the result is stored",
            examples=["s3://service-result-bucket/some-file"],
        ),
    ]

    size: Annotated[
        int | None,
        Field(
            title="Size of result",
            description="Size of the result in bytes if known",
            examples=[1238123, None],
        ),
    ] = None

    mime_type: Annotated[
        str | None,
        Field(
            title="MIME type of result",
            description="MIME type of the result if known",
            examples=["application/fits", "application/x-votable+xml", None],
        ),
    ] = None

    @classmethod
    def from_worker_result(cls, result: WorkerResult) -> Self:
        """Convert from the `~safir.arq.uws.WorkerResult` model."""
        return cls(
            id=result.result_id,
            url=result.url,
            size=result.size,
            mime_type=result.mime_type,
        )

    def to_xml_model(self) -> ResultReference:
        """Convert to a Pydantic XML model."""
        return ResultReference(
            id=self.id, size=self.size, mime_type=self.mime_type
        )


class SignedJobResult(JobResult):
    """A single result from the job with a signed URL.

    A `JobResult` is converted to a `SignedJobResult` before generating the
    response via templating or returning the URL as a redirect.
    """

    @override
    def to_xml_model(self) -> ResultReference:
        """Convert to a Pydantic XML model."""
        return ResultReference(
            id=self.id,
            type=None,
            href=self.url,
            size=self.size,
            mime_type=self.mime_type,
        )


class JobBase(BaseModel):
    """Fields common to all variations of the job record."""

    json_parameters: Annotated[
        dict[str, Any],
        Field(
            title="Job parameters",
            description=(
                "May be any JSON-serialized object. Stored opaquely and"
                " returned as part of the job record."
            ),
            examples=[
                {
                    "ids": ["data-id"],
                    "stencils": [
                        {
                            "type": "circle",
                            "center": [1.1, 2.1],
                            "radius": 0.001,
                        }
                    ],
                },
            ],
        ),
    ]

    run_id: Annotated[
        str | None,
        Field(
            title="Client-provided run ID",
            description=(
                "The run ID allows the client to add a unique identifier to"
                " all jobs that are part of a single operation, which may aid"
                " in tracing issues through a complex system or identifying"
                " which operation a job is part of"
            ),
            examples=["daily-2024-10-29"],
        ),
    ] = None

    destruction_time: Annotated[
        UtcDatetime,
        Field(
            title="Destruction time",
            description=(
                "At this time, the job will be aborted if it is still"
                " running, its results will be deleted, and it will either"
                " change phase to ARCHIVED or all record of the job will be"
                " discarded"
            ),
            examples=["2024-11-29T23:57:55+00:00"],
        ),
    ]

    execution_duration: Annotated[
        SecondsTimedelta | None,
        Field(
            title="Maximum execution duration",
            description=(
                "Allowed maximum execution duration. This is specified in"
                " elapsed wall clock time (not CPU time). If null, the"
                " execution time is unlimited. If the job runs for longer than"
                " this time period, it will be aborted."
            ),
        ),
        PlainSerializer(
            lambda t: int(t.total_seconds()) if t is not None else None,
            return_type=int,
        ),
    ] = None


class JobCreate(JobBase):
    """Information required to create a new UWS job (Wobbly format)."""


class SerializedJob(JobBase):
    """A single UWS job (Wobbly format)."""

    id: Annotated[
        str,
        Field(
            title="Job ID",
            description="Unique identifier of the job",
            examples=["47183"],
        ),
        BeforeValidator(lambda v: str(v) if isinstance(v, int) else v),
    ]

    service: Annotated[
        str,
        Field(
            title="Service",
            description="Service responsible for this job",
            examples=["vo-cutouts"],
        ),
    ]

    owner: Annotated[
        str,
        Field(
            title="Job owner",
            description="Identity of the owner of the job",
            examples=["someuser"],
        ),
    ]

    phase: Annotated[
        ExecutionPhase,
        Field(
            title="Execution phase",
            description="Current execution phase of the job",
            examples=[
                ExecutionPhase.PENDING,
                ExecutionPhase.EXECUTING,
                ExecutionPhase.COMPLETED,
            ],
        ),
    ]

    message_id: Annotated[
        str | None,
        Field(
            title="Work queue message ID",
            description=(
                "Internal message identifier for the work queuing system."
                " Only meaningful to the service that stored this ID."
            ),
            examples=["e621a175-e3bf-4a61-98d7-483cb5fb9ec2"],
        ),
    ] = None

    creation_time: Annotated[
        UtcDatetime,
        Field(
            title="Creation time",
            description="When the job was created",
            examples=["2024-10-29T23:57:55+00:00"],
        ),
    ]

    start_time: Annotated[
        UtcDatetime | None,
        Field(
            title="Start time",
            description="When the job started executing (if it has)",
            examples=["2024-10-30T00:00:21+00:00", None],
        ),
    ] = None

    end_time: Annotated[
        UtcDatetime | None,
        Field(
            title="End time",
            description="When the job stopped executing (if it has)",
            examples=["2024-10-30T00:08:45+00:00", None],
        ),
    ] = None

    quote: Annotated[
        UtcDatetime | None,
        Field(
            title="Expected completion time",
            description=(
                "Expected completion time of the job if it were started now,"
                " or null to indicate that the expected duration is not known."
                " If later than the destruction time, indicates that the job"
                " is not possible due to resource constraints."
            ),
        ),
    ] = None

    errors: Annotated[
        list[JobError],
        Field(
            title="Error", description="Error information if the job failed"
        ),
    ] = []

    results: Annotated[
        list[JobResult],
        Field(
            title="Job results",
            description="Results of the job, if it has finished",
        ),
    ] = []

    def to_job_description(self, base_url: str) -> ShortJobDescription:
        """Convert to the Pydantic XML model used for the summary of jobs.

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
            job_id=self.id,
            type=None,
            href=f"{base_url}/{self.id}",
        )


class Job[P: ParametersModel](SerializedJob):
    """A single UWS job with deserialized parameters."""

    parameters: Annotated[
        P,
        Field(
            title="Job parameters",
            description=(
                "Job parameters converted to their Pydantic model. Use"
                " ``json_parameters`` for the serialized form sent over"
                " the wire."
            ),
            exclude=True,
        ),
    ]

    @classmethod
    def from_serialized_job(
        cls, job: SerializedJob, parameters_type: type[P]
    ) -> Self:
        """Convert from a serialized job returned by Wobbly.

        Parameters
        ----------
        job
            Serialized job from Wobbly.
        parameters_type
            Model to use for job parameters.

        Returns
        -------
        Job
            Job with the correct parameters model.

        Raises
        ------
        pydantic.ValidationError
            Raised if the serialized parameters cannot be validated.
        """
        job_dict = job.model_dump()
        params = job_dict.get("json_parameters")
        if params:
            job_dict["parameters"] = parameters_type.model_validate(params)
        return cls.model_validate(job_dict)

    def to_serialized_job(self) -> SerializedJob:
        """Convert to a serialized job suitable for sending to Wobbly."""
        job = self.model_dump(mode="json")
        return SerializedJob.model_validate(job)

    def to_xml_model[S: JobSummary](self, job_summary_type: type[S]) -> S:
        """Convert to a Pydantic XML model.

        Parameters
        ----------
        job_summary_type
            XML model class for the job summary.

        Returns
        -------
        vo_models.uws.models.JobSummary
            XML model corresponding to this job.
        """
        results = None
        if self.results:
            results = Results(results=[r.to_xml_model() for r in self.results])
        duration = None
        if self.execution_duration:
            duration = int(self.execution_duration.total_seconds())
        error_summary = None
        if self.errors:
            error_summary = self.errors[0].to_xml_model()
        return job_summary_type(
            job_id=self.id,
            run_id=self.run_id,
            owner_id=self.owner,
            phase=self.phase,
            quote=self.quote,
            creation_time=self.creation_time,
            start_time=self.start_time,
            end_time=self.end_time,
            execution_duration=duration,
            destruction=self.destruction_time,
            parameters=self.parameters.to_xml_model(),
            results=results,
            error_summary=error_summary,
            version=UWSVersion.V1_1,
        )


class JobUpdateAborted(BaseModel):
    """Input model when aborting a job."""

    phase: Annotated[
        Literal[ExecutionPhase.ABORTED],
        Field(
            title="New phase",
            description="New phase of job",
            examples=[ExecutionPhase.ABORTED],
        ),
    ]


class JobUpdateCompleted(BaseModel):
    """Input model when marking a job as complete."""

    phase: Annotated[
        Literal[ExecutionPhase.COMPLETED],
        Field(
            title="New phase",
            description="New phase of job",
            examples=[ExecutionPhase.COMPLETED],
        ),
    ]

    results: Annotated[
        list[JobResult],
        Field(title="Job results", description="All the results of the job"),
    ]


class JobUpdateExecuting(BaseModel):
    """Input model when marking a job as executing."""

    phase: Annotated[
        Literal[ExecutionPhase.EXECUTING],
        Field(
            title="New phase",
            description="New phase of job",
            examples=[ExecutionPhase.EXECUTING],
        ),
    ]

    start_time: Annotated[
        UtcDatetime,
        Field(
            title="Start time",
            description="When the job started executing",
            examples=["2024-11-01T12:15:45+00:00"],
        ),
    ]


class JobUpdateError(BaseModel):
    """Input model when marking a job as failed."""

    phase: Annotated[
        Literal[ExecutionPhase.ERROR],
        Field(
            title="New phase",
            description="New phase of job",
            examples=[ExecutionPhase.ERROR],
        ),
    ]

    errors: Annotated[
        list[JobError],
        Field(
            title="Failure details",
            description="Job failure error message and details",
            min_length=1,
        ),
    ]


class JobUpdateQueued(BaseModel):
    """Input model when marking a job as queued."""

    phase: Annotated[
        Literal[ExecutionPhase.QUEUED],
        Field(
            title="New phase",
            description="New phase of job",
            examples=[ExecutionPhase.QUEUED],
        ),
    ]

    message_id: Annotated[
        str | None,
        Field(
            title="Queue message ID",
            description="Corresponding message within a job queuing system",
            examples=["4ce850a7-d877-4827-a3f6-f84534ec3fad"],
        ),
    ]


class JobUpdateMetadata(BaseModel):
    """Input model when updating job metadata."""

    phase: Annotated[
        None,
        Field(
            title="New phase", description="New phase of job", examples=[None]
        ),
    ] = None

    destruction_time: Annotated[
        UtcDatetime,
        Field(
            title="Destruction time",
            description=(
                "At this time, the job will be aborted if it is still"
                " running, its results will be deleted, and it will either"
                " change phase to ARCHIVED or all record of the job will be"
                " discarded"
            ),
            examples=["2024-11-29T23:57:55+00:00"],
        ),
    ]

    execution_duration: Annotated[
        SecondsTimedelta | None,
        Field(
            title="Maximum execution duration",
            description=(
                "Allowed maximum execution duration. This is specified in"
                " elapsed wall clock time (not CPU time). If null, the"
                " execution time is unlimited. If the job runs for longer than"
                " this time period, it will be aborted."
            ),
        ),
        PlainSerializer(
            lambda t: int(t.total_seconds()) if t else None,
            return_type=int | None,
        ),
    ]
