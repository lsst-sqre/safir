"""Tests for the Google Cloud Storage support infrastructure.

These are just basic sanity checks that the mocking is working correctly and
the basic calls work.
"""

from __future__ import annotations

from datetime import timedelta

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
