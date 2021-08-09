"""Standard models for FastAPI applications.

FastAPI does not appear to export its error response model in a usable form,
so define a copy of it so that we can reference it in API definitions to
generate good documentation.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

__all__ = ["ErrorModel"]


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
