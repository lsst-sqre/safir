"""Tests for FastAPI helper code."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from safir.fastapi import ClientRequestError, client_request_error_handler
from safir.models import ErrorLocation, ErrorModel


@pytest.mark.asyncio
async def test_client_request_error() -> None:
    app = FastAPI()
    app.exception_handler(ClientRequestError)(client_request_error_handler)

    class UnknownUserError(ClientRequestError):
        error = "unknown_user"
        status_code = status.HTTP_404_NOT_FOUND

    class InvalidAddressError(ClientRequestError):
        error = "invalid_address"

    class PermissionDeniedError(ClientRequestError):
        error = "permission_denied"
        status_code = status.HTTP_403_FORBIDDEN

    @app.get("/user")
    async def user_error() -> dict[str, str]:
        raise UnknownUserError("Unknown user", ErrorLocation.path, ["user"])

    @app.get("/address")
    async def address_error() -> dict[str, str]:
        try:
            raise InvalidAddressError("Invalid address")
        except ClientRequestError as e:
            e.location = ErrorLocation.body
            e.field_path = ["user", "address"]
            raise

    @app.get("/permission")
    async def permission_error() -> dict[str, str]:
        raise PermissionDeniedError("Permission denied")

    async with AsyncClient(app=app, base_url="https://example.com/") as client:
        r = await client.get("/user")
        assert r.status_code == 404
        assert r.json() == {
            "detail": [
                {
                    "msg": "Unknown user",
                    "type": "unknown_user",
                    "loc": ["path", "user"],
                }
            ]
        }

        r = await client.get("/address")
        assert r.status_code == 422
        error = ErrorModel.parse_obj(r.json())
        assert error.detail[0].loc == [ErrorLocation.body, "user", "address"]
        assert error.detail[0].msg == "Invalid address"
        assert error.detail[0].type == "invalid_address"

        r = await client.get("/permission")
        assert r.status_code == 403
        assert r.json() == {
            "detail": [
                {"msg": "Permission denied", "type": "permission_denied"}
            ]
        }
