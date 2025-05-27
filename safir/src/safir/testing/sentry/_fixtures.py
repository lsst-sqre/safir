"""Fixtures for captured Sentry information and transport.

Taken from the `Sentry Python SDK's unit tests
<https://github.com/getsentry/sentry-python/blob/c6a89d64db965fe0ece6de10df38ab936af8f5e4/tests/conftest.py>`__.
"""

# Copyright (c) 2018 Functional Software, Inc. dba Sentry
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

import contextlib
from collections.abc import Callable, Generator
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.envelope import Envelope

from ._mocks import Attachment, Captured, TestTransport

__all__ = [
    "capture_events_fixture",
    "sentry_init_fixture",
]


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
            msg = "Error patching Sentry transport: client.transport is None"
            raise RuntimeError(msg)
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
