"""Error models for FastAPI applications."""

from enum import StrEnum

from pydantic import BaseModel, Field

__all__ = [
    "ErrorDetail",
    "ErrorLocation",
    "ErrorModel",
]


class ErrorLocation(StrEnum):
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
