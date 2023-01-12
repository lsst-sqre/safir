"""Tests for the Google Cloud Storage support infrastructure.

These are just basic sanity checks that the mocking is working correctly and
the basic calls work.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import google.auth
import pytest
from google.auth import impersonated_credentials
from google.cloud import storage

from safir.testing.gcs import MockStorageClient


def test_mock(mock_gcs: MockStorageClient) -> None:
    client = storage.Client()
    bucket = client.bucket("some-bucket")
    blob = bucket.blob("something")
    credentials = google.auth.default()
    signing_credentials = impersonated_credentials.Credentials(
        source_credentials=credentials,
        target_principle="some-service-account",
        target_scopes="https://www.googleapis.com/auth/devstorage.read_only",
        lifetime=2,
    )
    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(hours=1),
        method="GET",
        response_type="application/fits",
        credentials=signing_credentials,
    )
    assert signed_url == "https://example.com/something"

    # The wrong expiration produces an assertion.
    with pytest.raises(AssertionError):
        blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=2),
            method="GET",
            response_type="application/fits",
            credentials=signing_credentials,
        )

    # The wrong bucket produces an assertion.
    with pytest.raises(AssertionError):
        bucket = client.bucket("wrong-bucket")


def test_mock_files(mock_gcs_file: MockStorageClient) -> None:
    this_file = Path(__file__)
    client = storage.Client()
    bucket = client.bucket("some-bucket")
    blob = bucket.blob(this_file.name)

    # Test that signed URLs still work.
    credentials = google.auth.default()
    signing_credentials = impersonated_credentials.Credentials(
        source_credentials=credentials,
        target_principle="some-service-account",
        target_scopes="https://www.googleapis.com/auth/devstorage.read_only",
        lifetime=2,
    )
    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(hours=1),
        method="GET",
        response_type="application/fits",
        credentials=signing_credentials,
    )
    assert signed_url == f"https://example.com/{this_file.name}"

    # Test the file-specific methods.
    assert blob.exists()
    assert blob.size == this_file.stat().st_size
    assert blob.updated == datetime.fromtimestamp(
        this_file.stat().st_mtime, tz=timezone.utc
    )
    assert blob.etag == str(this_file.stat().st_ino)
    assert blob.download_as_bytes() == this_file.read_bytes()
    with blob.open("rb") as f:
        contents = f.read()
    assert contents == this_file.read_bytes()

    # Test an invalid open mode.
    with pytest.raises(AssertionError):
        blob.open("wb")

    # Test a nonexistent file.
    blob = bucket.blob("does-not-exist")
    assert not blob.exists()


def test_mock_minimal(mock_gcs_minimal: MockStorageClient) -> None:
    """Minimal configuration, which doesn't check lifetime or bucket name."""
    client = storage.Client()
    bucket = client.bucket("some-bucket")

    # It doesn't matter what bucket name we choose, since we didn't request
    # verification.
    bucket = client.bucket("other-bucket")

    # It doesn't matter what expiration we specify on signed URLs.
    blob = bucket.blob("a-file")
    signed_url = blob.generate_signed_url(
        version="v4", expiration=timedelta(minutes=1), method="GET"
    )
    assert signed_url == "https://example.com/a-file"
    signed_url = blob.generate_signed_url(
        version="v4", expiration=timedelta(hours=1), method="GET"
    )
    assert signed_url == "https://example.com/a-file"
