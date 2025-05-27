"""Mocks for captured Sentry information and transport.

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

from dataclasses import dataclass
from typing import Any, override

from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

__all__ = [
    "Attachment",
    "Captured",
    "TestTransport",
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
