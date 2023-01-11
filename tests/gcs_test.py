"""Tests for Google Cloud Storage support code."""

from __future__ import annotations

from datetime import timedelta

import pytest

from safir.gcs import SignedURLService
from safir.testing.gcs import MockStorageClient


def test_signed_url(mock_gcs: MockStorageClient) -> None:
    url_service = SignedURLService(timedelta(hours=1), "service-account")
    url = url_service.signed_url("s3://some-bucket/path/to/blob", "text/plain")
    assert url == "https://example.com/path/to/blob"

    # Test that the lifetime is passed down to the mock, which will reject it
    # if it's not an hour.
    url_service = SignedURLService(timedelta(minutes=30), "foo")
    with pytest.raises(AssertionError):
        url_service.signed_url("s3://some-bucket/blob", "text/plain")
