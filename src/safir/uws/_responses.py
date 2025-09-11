"""Return internal objects as XML responses."""

from __future__ import annotations

try:
    import jinja2
except ImportError as e:
    raise ImportError(
        "The safir.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e
from fastapi import Request, Response
from fastapi.templating import Jinja2Templates

from safir.datetime import isodatetime

from ._models import JobError

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

    def error(self, request: Request, error: JobError) -> Response:
        """Return the error of a job as an XML response."""
        return _templates.TemplateResponse(
            request,
            "error.xml",
            {"error": error},
            media_type="application/xml",
        )
