#################################
Handling HTTP errors with FastAPI
#################################

FastAPI_ automatically generates HTTP errors for for some types of erroneous client requests, such as 422 errors when the input to a handler doesn't match its requirements.
Other errors are normally returned by raising `fastapi.HTTPException` with an appropriate ``status_code`` parameter.

Errors raised by FastAPI will have a JSON body that follows a standard syntax.
To provide standard error reporting for all application APIs, you may wish to return other errors using the same structure.

Defining structured client errors
=================================

The easiest way to return structured errors for invalid client requests is to define exceptions inheriting from `~safir.fastapi.ClientRequestError` and install the global `~safir.fastapi.client_request_error_handler` exception handler.
The combination of those two components will transform the exception into an HTTP reply with the correct error status and a properly-formatted JSON error body.

A typical application exception would look like this:

.. code-block:: python

   from fastapi import status
   from safir.fastapi import ClientRequestError


   class UnknownUserError(ClientRequestError):
       """Specified user is unknown."""

       error = "unknown_user"
       status_code = status.HTTP_404_NOT_FOUND

The exception should inherit from `~safir.fastapi.ClientRequestError` (possibly indirectly) and set the class variables ``error`` and ``status_code``.

``error`` should be set to some short identifier for this error.
This will be reported in the ``type`` field of the error message (see :ref:`structured-error-syntax`).

Then, in the application setup code of your FastAPI application, add a global error handler for all exceptions derived from `~safir.fastapi.ClientRequestError`:

.. code-block:: python

   from safir.fastapi import ClientRequestError, client_request_error_handler


   app.exception_handler(ClientRequestError)(client_request_error_handler)

Any uncaught exception derived from `~safir.fastapi.ClientRequestError` will be caught by this exception handler and transformed into a properly-formatted HTTP error response.

If your application reports uncaught exceptions to Slack (see :ref:`slack-uncaught-exceptions`), these exceptions will be marked so that they won't be reported.
(`~safir.fastapi.ClientRequestError` inherits from `~safir.slack.webhook.SlackIgnoredException`.)

Raising structured client errors
================================

Exceptions derived from `~safir.fastapi.ClientRequestError` can be raised like any other exception.
If the location of the data causing the error is known when the exception is raised, it can be specified in the optional ``location`` and ``field_path`` parameters to the exception constructor.
This data will populate the ``loc`` field of the client error.
(See :ref:`structured-error-syntax`.)

For example, if your code has defined an ``UnknownUserError`` and you know at the point where the exception is raised that the unknown user was specified in the ``user`` path parameter to the route, you would raise the exception like this:

.. code-block:: python

   from safir.models import ErrorLocation


   raise UnknownUserError("Unknown user", ErrorLocation.path, ["user"])

More commonly, the location information is only known to the handler, but the exception will be raised by internal service code.
In this case, do not specify ``location`` or ``field_path`` when raising the exception, and catch and re-raise the exception in the handler after adding additional location information.

For example, suppose the user specifies an invalid address in the ``address`` field of a ``user`` data structure in a JSON POST body, and you have defined an ``InvalidAddressError`` raised by your internal service code (which may have no idea where the address comes from).
Your code may look something like this:

.. code-block:: python

   from safir.models import ErrorLocation


   @router.post("/info/{username}")
   async def get_info(username: str, data: UserData) -> None:
       try:
           return set_user_data(username, data)
       except InvalidAddressError as e:
           e.location = ErrorLocation.post
           e.field_path = ["user", "address"]
           raise

.. _structured-error-syntax:

Syntax of FastAPI structured errors
===================================

`safir.models.ErrorModel` defines a Pydantic model compatible with the format used by FastAPI.
This consists of a ``detail`` key that takes a list of `safir.models.ErrorDetail` objects.
Each one has a ``type`` attribute, which contains a short unique identifier for the error, and a ``msg`` attribute, which contains the human-readable error message.
It optionally can also contain a ``loc`` attribute.

If present, the ``loc`` attribute is an ordered list of location keys identifing the specific input data that caused the error.
The first element of ``loc`` should be chosen from the values of `safir.models.ErrorLocation`.

For example, for an error in the ``job_id`` path variable, the value of ``loc`` would be ``[ErrorLocation.path, "job_id"]``.
For an error in a nested ``account`` element in a JSON object submitted in the body of a POST request, the value of ``loc`` might be ``[ErrorLocation.body, "config", "account"]``.
If the error is in the ``X-CSRF-Token`` header, the value of ``loc`` would be ``[ErrorLocation.header, "X-CSRF-Token"]``.

``loc`` may be omitted for errors not caused by a specific element of input data.

When using exceptions derived from `~safir.fastapi.ClientRequestError`, the first element of ``loc`` is specified by ``location`` and the remaining elements are specified by ``field_path``.

Raising structured errors without custom exceptions
===================================================

Sometimes it's easier to raise a structured error directly without defining a custom exception.

``fastapi.HTTPException`` supports a ``detail`` parameter that should include information about the cause of the error.
FastAPI accepts an arbitrary JSON-serializable data in that parameter, but for compatibility with the errors generated internally by FastAPI, the value should be an array of dict representations of `safir.models.ErrorDetail`.

The code to raise ``fastapi.HTTPException`` should therefore look something like this:

.. code-block:: python

   from safir.models import ErrorDetail, ErrorLocation


   error = ErrorDetail(
       loc=[ErrorLocation.path, "foo"],
       msg="There is no foo",
       type="unknown_foo",
   )
   raise HTTPException(
       status_code=status.HTTP_404_NOT_FOUND,
       detail=[error.dict(exclude_none=True)],
   )

Declaring the error model
=========================

To declare that a handler returns `safir.models.ErrorModel` for a given error code, use the ``responses`` attribute to either the route decorator or to ``include_router`` if it applies to all routes provided by a router.

For example, for a single route:

.. code-block:: python

   from safir.models import ErrorModel


   @router.get(
       "/route/{foo}",
       ...,
       responses={404: {"description": "Not found", "model": ErrorModel}},
   )
   async def route(foo: str) -> None:
       ...

If all routes provided by a router have the same error handling behavior for a given response code, it saves some effort to instead do this when including the router, normally in ``main.py``:

.. code-block:: python

   app.include_router(
       api.router,
       prefix="/auth/api/v1",
       responses={
           403: {"description": "Permission denied", "model": ErrorModel},
       },
   )
