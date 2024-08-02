"""Helper code for FastAPI (other than dependencies and middleware)."""

from ._errors import ClientRequestError, client_request_error_handler

__all__ = [
    "ClientRequestError",
    "client_request_error_handler",
]
