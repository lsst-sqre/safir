"""Standard models for FastAPI applications.

Examples
--------
To reference the `ErrorModel` model when returning an error message, use code
similar to this:

.. code-block:: python

   @router.get(
       "/route/{foo}",
       ...,
       responses={404: {"description": "Not found", "model": ErrorModel}},
   )
   async def route(foo: str) -> None:
       ...
       raise HTTPException(
           status_code=status.HTTP_404_NOT_FOUND,
           detail=[
               {"loc": ["path", "foo"], "msg": msg, "type": "invalid_foo"},
           ],
       )

Notes
-----
FastAPI does not appear to export its error response model in a usable form,
so define a copy of it so that we can reference it in API definitions to
generate good documentation.
"""

# Examples and notes kept in the module docstring because they're not
# appropriate for the API documentation generated for a service.

from typing import List, Optional

from pydantic import BaseModel, Field

__all__ = ["ErrorDetail", "ErrorModel"]


class ErrorDetail(BaseModel):
    """The detail of the error message."""

    loc: Optional[List[str]] = Field(
        None, title="Location", example=["area", "field"]
    )

    msg: str = Field(..., title="Message", example="Some error messge")

    type: str = Field(..., title="Error type", example="some_code")


class ErrorModel(BaseModel):
    """A structured API error message."""

    detail: List[ErrorDetail] = Field(..., title="Detail")
