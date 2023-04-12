"""Helper code for FastAPI (other than dependencies and middleware)."""

from __future__ import annotations

from typing import ClassVar, Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse

from .models import ErrorLocation
from .slack.webhook import SlackIgnoredException

__all__ = [
    "ClientRequestError",
    "client_request_error_handler",
]


class ClientRequestError(SlackIgnoredException):
    """Represents an error in a client request.

    This is a base class for exceptions representing expected errors in client
    requests. Expected here means that the error should result in a 4xx HTTP
    error code with an error message in the body and do not represent a server
    failure that should produce alerts. It should normally be used in
    conjunction with the `client_request_error_handler` exception handler.

    Exceptions inheriting from this class should set the class variable
    ``error`` to a unique error code (normally composed of lowercase letters
    and underscores) for that error, and the class variable ``status_code`` to
    the HTTP status code this exception should generate (if not 422, the
    default).

    Attributes
    ----------
    location
        The part of the request giving rise to the error. This can be set by
        catching the exception in the part of the code that knows where the
        data came from, setting this attribute, and re-raising the exception.
    field_path
        Field, as a hierarchical list of structure elements, within that part
        of the request giving rise to the error. As with ``location``, can be
        set by catching and re-raising.

    Parameters
    ----------
    message
        Error message, used as the ``msg`` key in the serialized error.
    location
        The part of the request giving rise to the error. This may be omitted
        if the error message does not have meaningful location information, or
        to set this information via the corresponding attribute in a later
        exception handler.
    field_path
        Field, as a hierarchical list of structure elements, within the
        ``location`` giving rise to the error. This may be omitted if the
        error message does not have meaningful location information, or to set
        this information via the corresponding attribute in a later exception
        handler.

    Examples
    --------
    This class is meant to be subclassed. For example:

    .. code-block:: python

       from fastapi import status
       from safir.fastapi import ClientRequestError


       class UnknownUserError(ClientRequestError):
           error = "unknown_user"
           status_code = status.HTTP_404_NOT_FOUND

    If the location of the error is known when it is raised, it can be passed
    to the constructor. If a given error message always stems from the same
    location information, override ``__init__`` of the corresponding child
    exception class to pass that location information to the parent
    constructor.

    More commonly, the location information is only known to the handler, but
    the exception will be raised by internal service code. In this case, do
    not specify ``location`` or ``field_path`` when raising the exception, and
    catch and re-raise the exception in the handler after adding additional
    location information. For instance:

    .. code-block:: python

       from safir.models import ErrorLocation


       @router.get("/info/{username}", response_model=UserInfo)
       async def get_info(username: str) -> UserInfo:
           try:
               return get_user_data(username)
           except UnknownUserError as e:
               e.location = ErrorLocation.path
               e.field_path = ["username"]
               raise

    ``field_path`` may be a hierarchical list of elements in a complex
    structure. For example, for a POST handler that accepts JSON and finds a
    problem in the ``address`` key of the ``user`` field, set ``field_path``
    to ``["user", "address"]``.

    Some errors, such as permission denied errors, will not have any
    meaningful associated location information. In this case, do not specify
    ``location`` or ``field_path``.

    Notes
    -----
    FastAPI_ uses a standard error model for internally-generated errors
    (mostly Pydantic_ validation errors), but doesn't provide a facility to
    generate errors in the same format. Safir provides the
    `~safir.models.ErrorModel` Pydantic model, this class, and the
    `client_request_error_handler` exception handler to fill in the gap.

    This class records the necessary information to generate a
    FastAPI-compatible error structure and knows how to serialize itself in
    the same structure as `~safir.models.ErrorModel` via the ``to_dict``
    method. The `client_request_error_handler` exception handler uses that
    facility to transform this exception into a
    `fastapi.responses.JSONResponse` with an appropriate status code.

    The FastAPI error serialization format supports returning multiple errors
    at a time as a list in the ``detail`` key. This functionality is not
    supported by this exception class.
    """

    error: ClassVar[str] = "validation_failed"
    """Used as the ``type`` field of the error message.

    Should be overridden by any subclass.
    """

    status_code: ClassVar[int] = status.HTTP_422_UNPROCESSABLE_ENTITY
    """HTTP status code for this type of validation error."""

    def __init__(
        self,
        message: str,
        location: Optional[ErrorLocation] = None,
        field_path: Optional[list[str]] = None,
    ) -> None:
        super().__init__(message)
        self.location = location
        self.field_path = field_path

    def to_dict(self) -> dict[str, list[str] | str]:
        """Convert the exception to a dictionary suitable for the exception.

        Returns
        -------
        dict
            Serialized error message in a format suitable as a member of the
            list passed to the ``detail`` parameter to a
            `fastapi.HTTPException`. It is designed to produce the same JSON
            structure as native FastAPI errors.

        Notes
        -----
        The format of the returned dictionary is the same as the serialization
        of `~safir.models.ErrorDetail`, and is meant to be one element in the
        list that is the value of the ``detail`` key.
        """
        result: dict[str, list[str] | str] = {
            "msg": str(self),
            "type": self.error,
        }
        if self.location:
            if self.field_path:
                result["loc"] = [self.location.value] + self.field_path
            else:
                result["loc"] = [self.location.value]
        return result


async def client_request_error_handler(
    request: Request, exc: ClientRequestError
) -> JSONResponse:
    """Exception handler for exceptions derived from `ClientRequestError`.

    Parameters
    ----------
    request
        Request that gave rise to the exception.
    exc
        Exception.

    Returns
    -------
    fastapi.JSONResponse
        Serialization of the exception following `~safir.models.ErrorModel`,
        which is compatible with the serialization format used internally by
        FastAPI.

    Examples
    --------
    This function should be installed as a global exception handler for a
    FastAPI app:

    .. code-block:: python

       from safir.fastapi import (
           ClientRequestError,
           client_request_error_handler,
       )

       app.exception_handler(ClientRequestError)(client_request_error_handler)
    """
    return JSONResponse(
        status_code=exc.status_code, content={"detail": [exc.to_dict()]}
    )
