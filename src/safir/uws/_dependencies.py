"""FastAPI dependencies for the UWS service.

The UWS FastAPI support is initialized by the parent application via this
dependency's ``initialize`` method. It then returns a `UWSFactory` on request
to individual route handlers, which in turn can create other needed objects.
"""

from typing import Annotated, Literal

from fastapi import Depends, Form, Query
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

try:
    from safir.arq import ArqMode, ArqQueue, MockArqQueue, RedisArqQueue
except ImportError as e:
    raise ImportError(
        "The safir.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e
from safir.dependencies.http_client import http_client_dependency
from safir.dependencies.logger import logger_dependency

from ._config import UWSConfig
from ._responses import UWSTemplates
from ._results import ResultStore
from ._service import JobService
from ._storage import JobStore

__all__ = [
    "UWSDependency",
    "UWSFactory",
    "create_phase_dependency",
    "runid_post_dependency",
    "uws_dependency",
]


class UWSFactory:
    """Build UWS components.

    Parameters
    ----------
    config
        UWS configuration.
    arq
        arq queue to use.
    result_store
        Signed URL generator for results.
    logger
        Logger to use.
    """

    def __init__(
        self,
        *,
        config: UWSConfig,
        result_store: ResultStore,
        arq: ArqQueue,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        self._config = config
        self._result_store = result_store
        self._arq = arq
        self._http_client = http_client
        self._logger = logger

    def create_result_store(self) -> ResultStore:
        """Return a wrapper around the result storage."""
        return self._result_store

    def create_job_service(self) -> JobService:
        """Create a new UWS job metadata service."""
        return JobService(
            config=self._config,
            arq_queue=self._arq,
            storage=self.create_job_store(),
            logger=self._logger,
        )

    def create_job_store(self) -> JobStore:
        """Create a new UWS job store."""
        return JobStore(self._config, self._http_client)

    def create_templates(self) -> UWSTemplates:
        """Create a new XML renderer for responses."""
        return UWSTemplates()


class UWSDependency:
    """Initializes UWS and provides a UWS factory as a dependency."""

    def __init__(self) -> None:
        self._arq: ArqQueue | None = None
        self._config: UWSConfig
        self._result_store: ResultStore

    async def __call__(
        self,
        http_client: Annotated[AsyncClient, Depends(http_client_dependency)],
        logger: Annotated[BoundLogger, Depends(logger_dependency)],
    ) -> UWSFactory:
        if not self._arq:
            raise RuntimeError("UWSDependency not initialized")
        return UWSFactory(
            config=self._config,
            result_store=self._result_store,
            arq=self._arq,
            http_client=http_client,
            logger=logger,
        )

    async def initialize(self, config: UWSConfig) -> None:
        """Initialize the UWS subsystem.

        Parameters
        ----------
        config
            UWS configuration.
        """
        self._config = config
        self._result_store = ResultStore(config)
        if not self._arq:
            if config.arq_mode == ArqMode.production:
                settings = config.arq_redis_settings
                self._arq = await RedisArqQueue.initialize(settings)
            else:
                self._arq = MockArqQueue()

    def override_arq_queue(self, arq_queue: ArqQueue) -> None:
        """Change the arq used in subsequent invocations.

        This method is probably only useful for the test suite.

        Parameters
        ----------
        arq_queue
            New arq queue.
        """
        self._arq = arq_queue


uws_dependency = UWSDependency()


async def create_phase_dependency(
    *,
    get_phase: Annotated[
        Literal["RUN"] | None,
        Query(title="Immediately start job", alias="phase"),
    ] = None,
    post_phase: Annotated[
        Literal["RUN"] | None,
        Form(title="Immediately start job", alias="phase"),
    ] = None,
) -> Literal["RUN"] | None:
    """Parse the optional phase parameter to an async job creation.

    Allow ``phase=RUN`` to be specified in either the query or the POST
    parameters, which says that the job should be immediately started.
    """
    return post_phase or get_phase


async def runid_post_dependency(
    *,
    runid: Annotated[
        str | None,
        Form(
            title="Run ID for job",
            description=(
                "An opaque string that is returned in the job metadata and"
                " job listings. May be used by the client to associate jobs"
                " with specific larger operations."
            ),
        ),
    ] = None,
) -> str | None:
    """Parse the run ID from POST parameters."""
    return runid
