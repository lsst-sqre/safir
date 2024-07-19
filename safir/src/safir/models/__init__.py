"""Standard models for FastAPI applications.

Notes
-----
FastAPI does not appear to export its error response model in a usable form,
so define a copy of it so that we can reference it in API definitions to
generate good documentation.
"""

from enum import Enum

from pydantic import BaseModel, Field

__all__ = [
    "ErrorDetail",
    "ErrorLocation",
    "ErrorModel",
]


class ErrorLocation(str, Enum):
    """Possible locations for an error.

    The first element of ``loc`` in `ErrorDetail` should be chosen from one of
    these values.
    """

    body = "body"
    header = "header"
    path = "path"
    query = "query"


class ErrorDetail(BaseModel):
    """The detail of the error message."""

    loc: list[str] | None = Field(
        None, title="Location", examples=[["area", "field"]]
    )

    msg: str = Field(..., title="Message", examples=["Some error messge"])

    type: str = Field(..., title="Error type", examples=["some_code"])


class ErrorModel(BaseModel):
    """A structured API error message."""

    detail: list[ErrorDetail] = Field(..., title="Detail")
