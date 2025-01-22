"""Tests for Sentry helpers."""

import pytest
import respx
import sentry_sdk
from httpx import AsyncClient, HTTPError, Response

from safir.sentry import SentryException, SentryWebException
from safir.testing.sentry import Captured


def test_env_fingerprint_before_send(
    sentry_fingerprint_items: Captured,
) -> None:
    sentry_sdk.capture_exception(Exception("some error"))
    (error,) = sentry_fingerprint_items.errors
    assert error["fingerprint"] == ["{{ default }}", "some_env"]


def test_sentry_exception_before_send(
    sentry_exception_items: Captured,
) -> None:
    class SomeError(SentryException): ...

    exc = SomeError("some error")
    exc.tags["woo"] = "hoo"
    exc.contexts["foo"] = {"bar": "baz"}

    sentry_sdk.capture_exception(exc)

    (error,) = sentry_exception_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["tags"] == {"woo": "hoo"}


def test_combined_before_send(sentry_combo_items: Captured) -> None:
    class SomeError(SentryException): ...

    exc = SomeError("some error")
    exc.tags["woo"] = "hoo"
    exc.contexts["foo"] = {"bar": "baz"}

    sentry_sdk.capture_exception(exc)

    (error,) = sentry_combo_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["fingerprint"] == ["{{ default }}", "some_env"]
    assert error["tags"] == {"woo": "hoo"}


def test_sentry_exception(sentry_exception_items: Captured) -> None:
    class SomeError(SentryException): ...

    exc = SomeError("some error")
    exc.tags["woo"] = "hoo"
    exc.contexts["foo"] = {"bar": "baz"}

    sentry_sdk.capture_exception(exc)

    (error,) = sentry_exception_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["tags"] == {"woo": "hoo"}


@pytest.mark.asyncio
async def test_sentry_web_exception(
    respx_mock: respx.Router, sentry_exception_items: Captured
) -> None:
    class SomeError(SentryWebException):
        pass

    respx_mock.get("https://example.org/").mock(return_value=Response(404))
    exception = None
    try:
        async with AsyncClient() as client:
            r = await client.get("https://example.org/")
            r.raise_for_status()
    except HTTPError as e:
        exception = SomeError.from_exception(e)
        assert str(exception) == "Status 404 from GET https://example.org/"
        sentry_sdk.capture_exception(exception)

    (error,) = sentry_exception_items.errors
    assert error["exception"]["values"][0]["type"] == (
        "test_sentry_web_exception.<locals>.SomeError"
    )
    assert error["exception"]["values"][0]["value"] == (
        "Status 404 from GET https://example.org/"
    )
    assert error["tags"] == {
        "httpx_request_method": "GET",
        "httpx_request_status": "404",
        "httpx_request_url": "https://example.org/",
    }
