#################################
Handling HTTP errors with FastAPI
#################################

FastAPI automatically returns some HTTP errors for the application, such as 422 errors when the input to a handler doesn't match its requirements.
Other errors are normally returned by raising ``fastapi.HTTPException`` with an appropriate ``status_code`` parameter.

Errors raised by FastAPI will have a JSON body that follows a standard syntax.
To provide standard error reporting for all application APIs, you may wish to return other errors using the same structure.

Raising structured errors
=========================

``fastapi.HTTPException`` supports a ``detail`` parameter that should include information about the cause of the error.
FastAPI accepts an arbitrary JSON-serializable data in that parameter, but for compatibility with the errors generated internally by FastAPI, the value should be an array of dict representations of `safir.models.ErrorDetail`.

The ``loc`` attribute of `~safir.models.ErrorDetail`, if present, is an ordered list of location keys identifing the specific input data that caused the error.
The first element of ``loc`` should be chosen from the values of `safir.models.ErrorLocation`.

For example, for an error in the ``job_id`` path variable, the value of ``loc`` would be ``[ErrorLocation.path, "job_id"]``.
For an error in a nested ``account`` element in the body, the value of ``loc`` might be ``[ErrorLocation.body, "config", "account"]``.
``loc`` may be omitted for errors not caused by a specific element of input data.

The code to raise ``fastapi.HTTPException`` should therefore look something like this:

.. code-block:: python

   raise HTTPException(
       status_code=status.HTTP_404_NOT_FOUND,
       detail=[
           {
               "loc": [ErrorLocation.path, "foo"],
               "msg": msg,
               "type": "invalid_foo",
           },
       ],
   )


Declaring the error model
=========================

To declare that a particular error code returns `safir.models.ErrorModel`, use the ``responses`` attribute to either the route decorator or to ``include_router`` if it applies to all routes provided by a router.

For example, for a single route:

.. code-block:: python

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
