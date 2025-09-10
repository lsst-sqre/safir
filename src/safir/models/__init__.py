"""Standard models for FastAPI applications.

Notes
-----
FastAPI does not appear to export its error response model in a usable form,
so define a copy of it so that we can reference it in API definitions to
generate good documentation.
"""

from ._errors import ErrorDetail, ErrorLocation, ErrorModel

__all__ = [
    "ErrorDetail",
    "ErrorLocation",
    "ErrorModel",
]
