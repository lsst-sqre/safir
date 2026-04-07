"""Fixtures for tests of the testing support infrastructure."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from safir.testing.gcs import MockStorageClient, patch_google_storage


@pytest.fixture
def mock_gcs_file() -> Iterator[MockStorageClient]:
    with patch_google_storage(
        path=Path(__file__).parent,
        expected_expiration=timedelta(hours=1),
        bucket_name="some-bucket",
    ) as mock:
        yield mock


@pytest.fixture
def mock_gcs_minimal() -> Iterator[MockStorageClient]:
    with patch_google_storage() as mock:
        yield mock
