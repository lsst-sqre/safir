"""Unit test helpers for Sentry instrumentation.

From the Sentry Python SDK's own unit tests:
https://github.com/getsentry/sentry-python/blob/c6a89d64db965fe0ece6de10df38ab936af8f5e4/tests/conftest.py
"""

import contextlib
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, override

import pytest
import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

__all__ = [
    "Attachment",
    "Captured",
    "TestTransport",
    "capture_events_fixture",
    "sentry_init_fixture",
]


@dataclass
class Attachment:
    """Contents and metadata of a Sentry attachment."""

    filename: str
    bytes: bytes
    content_type: str


@dataclass
class Captured:
    """A container for interesting items sent to Sentry."""

    errors: list[dict[str, Any]]
    transactions: list[dict[str, Any]]
    attachments: list[Attachment]


class TestTransport(Transport):
    """A transport that doesn't actually transport anything."""

    def __init__(self) -> None:
        Transport.__init__(self)

    @override
    def capture_envelope(self, envelope: Envelope) -> None:
        """No-op capture_envelope for tests."""


@contextlib.contextmanager
def sentry_init_fixture() -> Generator[Callable[..., None]]:
    """Return an init function that injects a no-op transport."""

    def inner(*a: Any, **kw: Any) -> None:
        kw.setdefault("transport", TestTransport())
        client = sentry_sdk.Client(*a, **kw)
        sentry_sdk.get_global_scope().set_client(client)

    old_client = sentry_sdk.get_global_scope().client
    try:
        sentry_sdk.get_current_scope().set_client(None)
        yield inner
    finally:
        sentry_sdk.get_global_scope().set_client(old_client)


def capture_events_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[], Captured]:
    """Return a function that returns a container with items sent to Sentry."""

    def inner() -> Captured:
        test_client = sentry_sdk.get_client()
        if test_client.transport is None:
            raise RuntimeError(
                "Error patching Sentry transport: client.transport is None"
            )
        old_capture_envelope = test_client.transport.capture_envelope

        captured = Captured(errors=[], transactions=[], attachments=[])

        def append(envelope: Envelope) -> None:
            for item in envelope:
                match item.headers.get("type"):
                    case "event":
                        if item.payload.json is None:
                            raise ValueError(
                                "Sentry event unexpectedly missing json"
                                " payload"
                            )
                        captured.errors.append(item.payload.json)
                    case "transaction":
                        if item.payload.json is None:
                            raise ValueError(
                                "Sentry transaction unexpectedly missing json"
                                " payload"
                            )
                        captured.transactions.append(item.payload.json)
                    case "attachment":
                        captured.attachments.append(
                            Attachment(
                                filename=item.headers["filename"],
                                bytes=item.payload.get_bytes(),
                                content_type=item.headers["content_type"],
                            )
                        )
                    case _:
                        pass
            return old_capture_envelope(envelope)

        monkeypatch.setattr(test_client.transport, "capture_envelope", append)

        return captured

    return inner
