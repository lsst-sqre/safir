"""Configuration for the UWS service."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generic, Self, TypeAlias, TypeVar

from arq.connections import RedisSettings
from pydantic import BaseModel, Field, SecretStr
from pydantic_core import Url
from pydantic_settings import BaseSettings

from safir.arq import ArqMode, build_arq_redis_settings
from safir.pydantic import (
    EnvAsyncPostgresDsn,
    EnvRedisDsn,
    HumanTimedelta,
    SecondsTimedelta,
)

from ._models import UWSJob, UWSJobParameter

DestructionValidator: TypeAlias = Callable[[datetime, UWSJob], datetime]
"""Type for a validator for a new destruction time."""

ExecutionDurationValidator: TypeAlias = Callable[
    [timedelta, UWSJob], timedelta
]
"""Type for a validator for a new execution duration."""

T = TypeVar("T", bound=BaseModel)
"""Generic type for the worker parameters."""

__all__ = [
    "ParametersModel",
    "T",
    "UWSAppSettings",
    "UWSConfig",
    "UWSRoute",
]


@dataclass
class UWSRoute:
    """Defines a FastAPI dependency to get the UWS job parameters."""

    dependency: Callable[..., Coroutine[None, None, list[UWSJobParameter]]]
    """Type for a dependency that gathers parameters for a job."""

    summary: str
    """Summary string for API documentation."""

    description: str | None = None
    """Description string for API documentation."""


class ParametersModel(BaseModel, ABC, Generic[T]):
    """Defines the interface for a model suitable for job parameters."""

    @classmethod
    @abstractmethod
    def from_job_parameters(cls, params: list[UWSJobParameter]) -> Self:
        """Validate generic UWS parameters and convert to the internal model.

        Parameters
        ----------
        params
            Generic input job parameters.

        Returns
        -------
        ParametersModel
            Parsed cutout parameters specific to service.

        Raises
        ------
        safir.uws.MultiValuedParameterError
            Raised if multiple parameters are provided but not supported.
        safir.uws.ParameterError
            Raised if one of the parameters could not be parsed.
        pydantic.ValidationError
            Raised if the parameters do not validate.
        """

    @abstractmethod
    def to_worker_parameters(self) -> T:
        """Convert to the domain model used by the backend worker."""


@dataclass
class UWSConfig:
    """Configuration for the UWS service.

    The UWS service may be embedded in a variety of VO applications. This
    class encapsulates the configuration of the UWS component that may vary by
    service or specific installation.
    """

    arq_mode: ArqMode
    """What mode to use for the arq queue."""

    arq_redis_settings: RedisSettings
    """Settings for Redis for the arq queue."""

    async_post_route: UWSRoute
    """Route configuration for creating an async job via POST.

    The FastAPI dependency included in this object should expect POST
    parameters and return a list of `~safir.uws.UWSJobParameter` objects
    representing the job parameters.
    """

    database_url: str | Url
    """URL for the metadata database."""

    execution_duration: timedelta
    """Maximum execution time in seconds.

    Jobs that run longer than this length of time will be automatically
    aborted.
    """

    lifetime: timedelta
    """The lifetime of jobs.

    After this much time elapses since the creation of the job, all of the
    results from the job will be cleaned up and all record of the job will be
    deleted.
    """

    parameters_type: type[ParametersModel]
    """Type representing the job parameters.

    This will be used to validate parameters and to parse them before passing
    them to the worker.
    """

    signing_service_account: str
    """Email of service account to use for signed URLs.

    The default credentials that the application frontend runs with must have
    the ``roles/iam.serviceAccountTokenCreator`` role on the service account
    with this email.
    """

    worker: str
    """Name of the backend worker to call to execute a job."""

    database_password: SecretStr | None = None
    """Password for the database."""

    slack_webhook: SecretStr | None = None
    """Slack incoming webhook for reporting errors."""

    sync_get_route: UWSRoute | None = None
    """Route configuration for creating a sync job via GET.

    The FastAPI dependency included in this object should expect GET
    parameters and return a list of `~safir.uws.UWSJobParameter` objects
    representing the job parameters. If `None`, no route to create a job via
    sync GET will be created.
    """

    sync_post_route: UWSRoute | None = None
    """Route configuration for creating a sync job via POST.

    The FastAPI dependency included in this object should expect POST
    parameters and return a list of `~safir.uws.UWSJobParameter` objects
    representing the job parameters. If `None`, no route to create a job via
    sync POST will be created.
    """

    sync_timeout: timedelta = timedelta(minutes=5)
    """Maximum lifetime of a sync request."""

    url_lifetime: timedelta = timedelta(minutes=15)
    """How long result URLs should be valid for."""

    validate_destruction: DestructionValidator | None = None
    """Validate a new destruction time for a job.

    If provided, called with the requested destruction time and the current
    job record and should return the new destruction time. Otherwise, any
    destruction time before the configured maximum lifetime will be allowed.
    """

    validate_execution_duration: ExecutionDurationValidator | None = None
    """Validate a new execution duration for a job.

    If provided, called with the requested execution duration and the current
    job record and should return the new execution duration time. Otherwise,
    the execution duration may not be changed.
    """

    wait_timeout: timedelta = timedelta(minutes=1)
    """Maximum time a client can wait for a job change."""


class UWSAppSettings(BaseSettings):
    """Settings common to all applications using the UWS library.

    The ``Config`` class for an application should inherit from this class to
    get the standard UWS application settings.
    """

    arq_mode: ArqMode = Field(
        ArqMode.production,
        title="arq operation mode",
        description="This will always be production outside the test suite",
    )

    arq_queue_url: EnvRedisDsn = Field(
        ...,
        title="arq Redis DSN",
        description="DSN of Redis server to use for the arq queue",
    )

    arq_queue_password: SecretStr | None = Field(
        None,
        title="Password for arq Redis server",
        description="Password of Redis server to use for the arq queue",
    )

    database_url: EnvAsyncPostgresDsn = Field(
        ...,
        title="PostgreSQL DSN",
        description="DSN of PostgreSQL database for UWS job tracking",
    )

    database_password: SecretStr | None = Field(
        None, title="Password for UWS job database"
    )

    grace_period: SecondsTimedelta = Field(
        timedelta(seconds=30),
        title="Grace period for jobs",
        description=(
            "How long to wait for a job to finish on shutdown before"
            " canceling it"
        ),
    )

    lifetime: HumanTimedelta = Field(
        timedelta(days=7), title="Lifetime of job results"
    )

    service_account: str = Field(
        ...,
        title="Service account for URL signing",
        description=(
            "Email of the service account to use for signed URLs of results."
            " The default credentials that the application frontend runs with"
            " must have the ``roles/iam.serviceAccountTokenCreator`` role on"
            " the service account with this email."
        ),
    )

    storage_url: str = Field(
        ...,
        title="Root URL for cutout results",
        description=(
            "Must be a ``gs`` or ``s3`` URL pointing to a Google Cloud Storage"
            " bucket that is writable by the backend and readable by the"
            " frontend."
        ),
    )

    sync_timeout: HumanTimedelta = Field(
        timedelta(minutes=1), title="Timeout for sync requests"
    )

    timeout: SecondsTimedelta = Field(
        timedelta(minutes=10),
        title="Job timeout in seconds",
        description=(
            "Must be given as a number of seconds as a string or integer"
        ),
    )

    @property
    def arq_redis_settings(self) -> RedisSettings:
        """Redis settings for arq."""
        return build_arq_redis_settings(
            self.arq_queue_url, self.arq_queue_password
        )

    def build_uws_config(
        self,
        *,
        async_post_route: UWSRoute,
        parameters_type: type[ParametersModel],
        slack_webhook: SecretStr | None = None,
        sync_get_route: UWSRoute | None = None,
        sync_post_route: UWSRoute | None = None,
        url_lifetime: timedelta = timedelta(minutes=15),
        validate_destruction: DestructionValidator | None = None,
        validate_execution_duration: ExecutionDurationValidator | None = None,
        wait_timeout: timedelta = timedelta(minutes=1),
        worker: str,
    ) -> UWSConfig:
        """Construct a `UWSConfig` object from the application configuration.

        This helper method can be used by application ``Config`` classes to
        help build the `UWSConfig` object corresponding to the application
        configuration. Its parameters are the additional settings accepted by
        the UWS library that are not part of the ``UWSAppSettings`` model.

        Returns
        -------
        UWSConfig
            UWS configuration.

        Parameters
        ----------
        async_post_route
            Route configuration for job parameters for an async job via
            POST. The FastAPI dependency included in this object should expect
            POST parameters and return a list of `~safir.uws.UWSJobParameter`
            objects representing the job parameters.
        parameters_type
            Type representing the job parameters. This will be used to
            validate parameters and to parse them before passing them to the
            worker.
        slack_webhook
            Slack incoming webhook for reporting errors.
        sync_get_route
            Route configuration for creating a sync job via GET. The FastAPI
            dependency included in this object should expect GET parameters
            and return a list of `~safir.uws.UWSJobParameter` objects
            representing the job parameters. If `None`, no route to create a
            job via sync GET will be created.
        sync_post_route
            Route configuration for creating a sync job via POST. The FastAPI
            dependency included in this object should expect POST parameters
            and return a list of `~safir.uws.UWSJobParameter` objects
            representing the job parameters. If `None`, no route to create a
            job via sync POST will be created.
        url_lifetime
            How long result URLs should be valid for.
        validate_destruction
            Validate a new destruction time for a job. If provided, called
            with the requested destruction time and the current job record and
            should return the new destruction time. Otherwise, any destruction
            time before the configured maximum lifetime will be allowed.
        validate_execution_duration
            Validate a new execution duration for a job. If provided, called
            with the requested execution duration and the current job record
            and should return the new execution duration time. Otherwise, the
            execution duration may not be changed.
        wait_timeout
            Maximum time a client can wait for a job change.
        worker
            Name of the backend worker to call to execute a job.

        Examples
        --------
        Normally, this method is used from a property method that returns the
        UWS configuration, such as the following example for a cutout service:

        .. code-block:: python

           @property
           def uws_config(self) -> UWSConfig:
               return self.build_uws_config(
                   async_post_route=UWSRoute(
                       dependency=post_params_dependency,
                       summary="Create async cutout job",
                   ),
                   parameters_type=CutoutParameters,
                   slack_webhook=self.slack_webhook,
                   sync_get_route=UWSRoute(
                       dependency=get_params_dependency,
                       summary="Synchronous cutout",
                   ),
                   sync_post_route=UWSRoute(
                       dependency=post_params_dependency,
                       summary="Synchronous cutout",
                   ),
                   worker="cutout",
               )
        """
        return UWSConfig(
            arq_mode=self.arq_mode,
            arq_redis_settings=self.arq_redis_settings,
            execution_duration=self.timeout,
            lifetime=self.lifetime,
            parameters_type=parameters_type,
            signing_service_account=self.service_account,
            worker=worker,
            database_url=self.database_url,
            database_password=self.database_password,
            slack_webhook=slack_webhook,
            sync_timeout=self.sync_timeout,
            async_post_route=async_post_route,
            sync_get_route=sync_get_route,
            sync_post_route=sync_post_route,
            url_lifetime=url_lifetime,
            validate_destruction=validate_destruction,
            validate_execution_duration=validate_execution_duration,
            wait_timeout=wait_timeout,
        )
