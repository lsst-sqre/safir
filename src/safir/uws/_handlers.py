"""Handlers for the UWS API to a service.

The handlers defined in ``uws_router`` should be reusable for any IVOA service
that implements UWS. The other functions dynamically define additional
handlers that use dependencies provided by the application, so that the
application can define the parameters to a job.
"""

from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse

try:
    from vo_models.uws import Jobs, JobSummary, Results
    from vo_models.uws.types import ExecutionPhase
except ImportError as e:
    raise ImportError(
        "The safir.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e

from safir.datetime import isodatetime
from safir.dependencies.gafaelfawr import (
    auth_delegated_token_dependency,
    auth_dependency,
)
from safir.pydantic import IvoaIsoDatetime
from safir.slack.webhook import SlackRouteErrorHandler

from ._config import UWSRoute
from ._dependencies import (
    UWSFactory,
    create_phase_dependency,
    runid_post_dependency,
    uws_dependency,
)
from ._exceptions import DataMissingError
from ._models import ParametersModel

uws_router = APIRouter(route_class=SlackRouteErrorHandler)
"""FastAPI router for all external handlers."""

__all__ = [
    "install_async_post_handler",
    "install_availability_handler",
    "install_sync_get_handler",
    "install_sync_post_handler",
    "uws_router",
]


@uws_router.get(
    "",
    description=(
        "List all existing jobs for the current user. Jobs will be sorted"
        " by creation date, with the most recently created listed first."
    ),
    responses={
        200: {
            "content": {
                "application/xml": {"schema": Jobs.model_json_schema()}
            }
        }
    },
    summary="Async job list",
)
async def get_job_list(
    *,
    request: Request,
    phase: Annotated[
        list[ExecutionPhase] | None,
        Query(
            title="Execution phase",
            description="Limit results to the provided execution phases",
        ),
    ] = None,
    after: Annotated[
        datetime | None,
        Query(
            title="Creation date",
            description="Limit results to jobs created after this date",
        ),
    ] = None,
    last: Annotated[
        int | None,
        Query(
            title="Number of jobs",
            description="Return at most the given number of jobs",
        ),
    ] = None,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> Response:
    job_service = uws_factory.create_job_service()
    jobs = await job_service.list_jobs(
        token,
        base_url=str(request.url_for("get_job_list")),
        phases=phase,
        after=after,
        count=last,
    )
    xml = jobs.to_xml(skip_empty=True)
    return Response(content=xml, media_type="application/xml")


@uws_router.get(
    "/{job_id}",
    responses={
        200: {
            "content": {
                "application/xml": {"schema": JobSummary.model_json_schema()}
            }
        }
    },
    summary="Job details",
)
async def get_job(
    job_id: str,
    *,
    request: Request,
    wait: Annotated[
        int | None,
        Query(
            title="Wait for status changes",
            description=(
                "Maximum number of seconds to wait or -1 to wait for as long"
                " as the server permits"
            ),
        ),
    ] = None,
    phase: Annotated[
        ExecutionPhase | None,
        Query(
            title="Initial phase for waiting",
            description=(
                "When waiting for status changes, consider this to be the"
                " initial execution phase. If the phase has already changed,"
                " return immediately. This parameter should always be"
                " provided when wait is used."
            ),
        ),
    ] = None,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> Response:
    job_service = uws_factory.create_job_service()
    result_store = uws_factory.create_result_store()
    job = await job_service.get_summary(
        token, job_id, signer=result_store, wait_seconds=wait, wait_phase=phase
    )
    xml = job.to_xml(skip_empty=True)
    return Response(content=xml, media_type="application/xml")


@uws_router.delete(
    "/{job_id}",
    status_code=303,
    response_class=RedirectResponse,
    summary="Delete a job",
)
async def delete_job(
    job_id: str,
    *,
    request: Request,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    await job_service.delete(token, job_id)
    return str(request.url_for("get_job_list"))


@uws_router.post(
    "/{job_id}",
    description=(
        "Alternate job deletion mechanism for clients that cannot use DELETE."
    ),
    response_class=RedirectResponse,
    status_code=303,
    summary="Delete a job",
)
async def delete_job_via_post(
    job_id: str,
    *,
    action: Annotated[
        Literal["DELETE"] | None,
        Form(
            title="Action to perform",
            description="Mandatory, must be set to DELETE",
        ),
    ] = None,
    request: Request,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    await job_service.delete(token, job_id)
    return str(request.url_for("get_job_list"))


@uws_router.get(
    "/{job_id}/destruction",
    response_class=PlainTextResponse,
    summary="Destruction time for job",
)
async def get_job_destruction(
    job_id: str,
    *,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    job = await job_service.get(token, job_id)
    return isodatetime(job.destruction_time)


@uws_router.post(
    "/{job_id}/destruction",
    response_class=RedirectResponse,
    status_code=303,
    summary="Change job destruction time",
)
async def post_job_destruction(
    job_id: str,
    *,
    destruction: Annotated[
        IvoaIsoDatetime,
        Form(
            title="New destruction time",
            description="Must be in ISO 8601 format.",
            examples=["2021-09-10T10:01:02Z"],
        ),
    ],
    request: Request,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    await job_service.update_destruction(token, job_id, destruction)
    return str(request.url_for("get_job", job_id=job_id))


@uws_router.get(
    "/{job_id}/error",
    responses={
        200: {"content": {"application/x-votable+xml": {}}},
        404: {"description": "Job not found or job did not fail"},
    },
    summary="Job error",
)
async def get_job_error(
    job_id: str,
    *,
    request: Request,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> Response:
    job_service = uws_factory.create_job_service()
    errors = await job_service.get_error(token, job_id)
    if not errors:
        raise DataMissingError(f"Job {job_id} did not fail")
    templates = uws_factory.create_templates()

    # Wobbly supports storing multiple errors for a job, but currently the
    # templating into a VOTable only supports a single error and the code to
    # store the error only stores a single error. For now, return only the
    # first element of the list of errors.
    return templates.error(request, errors[0])


@uws_router.get(
    "/{job_id}/executionduration",
    response_class=PlainTextResponse,
    summary="Execution duration of job",
)
async def get_job_execution_duration(
    job_id: str,
    *,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    job = await job_service.get(token, job_id)
    if job.execution_duration:
        return str(int(job.execution_duration.total_seconds()))
    else:
        return "0"


@uws_router.post(
    "/{job_id}/executionduration",
    response_class=RedirectResponse,
    status_code=303,
    summary="Change job execution duration",
)
async def post_job_execution_duration(
    job_id: str,
    *,
    executionduration: Annotated[
        int,
        Form(
            title="New execution duration",
            description="Integer seconds of wall clock time.",
            examples=[14400],
            ge=0,
        ),
    ],
    request: Request,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    duration = None
    if executionduration > 0:
        duration = timedelta(seconds=executionduration)
    await job_service.update_execution_duration(token, job_id, duration)
    return str(request.url_for("get_job", job_id=job_id))


@uws_router.get(
    "/{job_id}/owner",
    response_class=PlainTextResponse,
    summary="Owner of job",
)
async def get_job_owner(
    job_id: str,
    *,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    job = await job_service.get(token, job_id)
    return job.owner


@uws_router.get(
    "/{job_id}/parameters",
    responses={200: {"content": {"application/xml": {}}}},
    summary="Job parameters",
)
async def get_job_parameters(
    job_id: str,
    *,
    request: Request,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> Response:
    job_service = uws_factory.create_job_service()
    job = await job_service.get_summary(token, job_id)
    if not job.parameters:
        raise DataMissingError(f"Job {job_id} has no parameters")
    xml = job.parameters.to_xml(skip_empty=True)
    return Response(content=xml, media_type="application/xml")


@uws_router.get(
    "/{job_id}/phase",
    response_class=PlainTextResponse,
    summary="Phase of job",
)
async def get_job_phase(
    job_id: str,
    *,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    job = await job_service.get(token, job_id)
    return job.phase.value


@uws_router.post(
    "/{job_id}/phase",
    response_class=RedirectResponse,
    status_code=303,
    summary="Start or abort job",
)
async def post_job_phase(
    job_id: str,
    *,
    phase: Annotated[
        Literal["RUN", "ABORT"] | None,
        Form(
            title="Job state change",
            summary="RUN to start the job, ABORT to abort the job.",
        ),
    ] = None,
    request: Request,
    user: Annotated[str, Depends(auth_dependency)],
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    if phase == "ABORT":
        await job_service.abort(token, job_id)
    elif phase == "RUN":
        await job_service.start(token, user, job_id)
    return str(request.url_for("get_job", job_id=job_id))


@uws_router.get(
    "/{job_id}/quote",
    response_class=PlainTextResponse,
    summary="Quote for job",
)
async def get_job_quote(
    job_id: str,
    *,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> str:
    job_service = uws_factory.create_job_service()
    job = await job_service.get(token, job_id)
    if job.quote:
        return isodatetime(job.quote)
    else:
        # The UWS standard says to return an empty text/plain response in this
        # case, as weird as it might look.
        return ""


@uws_router.get(
    "/{job_id}/results",
    responses={
        200: {
            "content": {
                "application/xml": {"schema": Results.model_json_schema()}
            }
        }
    },
    summary="Job results",
)
async def get_job_results(
    job_id: str,
    *,
    request: Request,
    token: Annotated[str, Depends(auth_delegated_token_dependency)],
    uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
) -> Response:
    job_service = uws_factory.create_job_service()
    result_store = uws_factory.create_result_store()
    job = await job_service.get_summary(token, job_id, signer=result_store)
    if not job.results:
        raise DataMissingError(f"Job {job_id} has no results")
    xml = job.results.to_xml(skip_empty=True)
    return Response(content=xml, media_type="application/xml")


def install_availability_handler(router: APIRouter) -> None:
    """Construct a default handler for the VOSI ``/availability`` interface.

    Parameters
    ----------
    router
        Router into which to install the handler.
    """

    @router.get(
        "/availability",
        description="VOSI-availability resource for the service",
        responses={200: {"content": {"application/xml": {}}}},
        summary="IVOA service availability",
    )
    async def get_availability(
        request: Request,
        uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
    ) -> Response:
        job_service = uws_factory.create_job_service()
        availability = await job_service.availability()
        xml = availability.to_xml(skip_empty=True)
        return Response(content=xml, media_type="application/xml")


def install_async_post_handler(router: APIRouter, route: UWSRoute) -> None:
    """Construct the POST handler for creating an async job.

    Parameters
    ----------
    router
        Router into which to install the handler.
    route
        Configuration for this route.
    """

    @router.post(
        "/jobs",
        response_class=RedirectResponse,
        status_code=303,
        summary=route.summary,
        description=route.description,
    )
    async def create_job(
        *,
        request: Request,
        phase: Annotated[
            Literal["RUN"] | None, Depends(create_phase_dependency)
        ] = None,
        parameters: Annotated[ParametersModel, Depends(route.dependency)],
        runid: Annotated[str | None, Depends(runid_post_dependency)],
        user: Annotated[str, Depends(auth_dependency)],
        token: Annotated[str, Depends(auth_delegated_token_dependency)],
        uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
    ) -> str:
        job_service = uws_factory.create_job_service()
        job = await job_service.create(token, parameters, run_id=runid)
        if phase == "RUN":
            await job_service.start(token, user, job.id)
        return str(request.url_for("get_job", job_id=job.id))


def install_sync_post_handler(router: APIRouter, route: UWSRoute) -> None:
    """Construct the POST handler for creating a sync job.

    Parameters
    ----------
    router
        Router into which to install the handler.
    route
        Configuration for this route.
    """

    @router.post(
        "/sync",
        response_class=RedirectResponse,
        status_code=303,
        summary=route.summary,
        description=route.description,
    )
    async def post_sync(
        *,
        runid: Annotated[str | None, Depends(runid_post_dependency)],
        parameters: Annotated[ParametersModel, Depends(route.dependency)],
        user: Annotated[str, Depends(auth_dependency)],
        token: Annotated[str, Depends(auth_delegated_token_dependency)],
        uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
    ) -> str:
        job_service = uws_factory.create_job_service()
        result_store = uws_factory.create_result_store()
        result = await job_service.run_sync(
            token, user, parameters, runid=runid
        )
        return result_store.sign_url(result).url


def install_sync_get_handler(router: APIRouter, route: UWSRoute) -> None:
    """Construct the GET handler for creating a sync job.

    Parameters
    ----------
    router
        Router into which to install the handler.
    route
        Configuration for this route.
    """

    @router.get(
        "/sync",
        response_class=RedirectResponse,
        status_code=303,
        summary=route.summary,
        description=route.description,
    )
    async def get_sync(
        *,
        runid: Annotated[
            str | None,
            Query(
                title="Run ID for job",
                description=(
                    "An opaque string that is returned in the job metadata and"
                    " job listings. May be used by the client to associate"
                    " jobs with specific larger operations."
                ),
            ),
        ] = None,
        parameters: Annotated[ParametersModel, Depends(route.dependency)],
        user: Annotated[str, Depends(auth_dependency)],
        token: Annotated[str, Depends(auth_delegated_token_dependency)],
        uws_factory: Annotated[UWSFactory, Depends(uws_dependency)],
    ) -> str:
        job_service = uws_factory.create_job_service()
        result_store = uws_factory.create_result_store()
        result = await job_service.run_sync(
            token, user, parameters, runid=runid
        )
        return result_store.sign_url(result).url
