"""Return internal objects as XML responses."""

from __future__ import annotations

import jinja2
from fastapi import Request, Response
from fastapi.templating import Jinja2Templates

from safir.datetime import isodatetime

from ._models import UWSJob, UWSJobError
from ._results import ResultStore

__all__ = ["UWSTemplates"]

_environment = jinja2.Environment(
    loader=jinja2.PackageLoader("safir", "uws/templates"),
    undefined=jinja2.StrictUndefined,
    autoescape=True,
)
_environment.filters["isodatetime"] = isodatetime
_templates = Jinja2Templates(env=_environment)


class UWSTemplates:
    """Template responses for the UWS protocol.

    This also includes VOSI-Availability since it was convenient to provide.
    """

    def __init__(self, result_store: ResultStore) -> None:
        self._result_store = result_store

    def error(self, request: Request, error: UWSJobError) -> Response:
        """Return the error of a job as an XML response."""
        return _templates.TemplateResponse(
            request,
            "error.xml",
            {"error": error},
            media_type="application/xml",
        )

    async def job(self, request: Request, job: UWSJob) -> Response:
        """Return a job as an XML response."""
        results = [self._result_store.sign_url(r) for r in job.results]
        return _templates.TemplateResponse(
            request,
            "job.xml",
            {"job": job, "results": results},
            media_type="application/xml",
        )

    def parameters(self, request: Request, job: UWSJob) -> Response:
        """Return the parameters for a job as an XML response."""
        return _templates.TemplateResponse(
            request,
            "parameters.xml",
            {"job": job},
            media_type="application/xml",
        )
