"""Fixtures for tests of the testing support infrastructure."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from safir.testing.gcs import MockStorageClient, patch_google_storage


@pytest.fixture
def mock_gcs_file() -> Iterator[MockStorageClient]:
    yield from patch_google_storage(
        path=Path(__file__).parent,
        expected_expiration=timedelta(hours=1),
        bucket_name="some-bucket",
    )


@pytest.fixture
def mock_gcs_minimal() -> Iterator[MockStorageClient]:
    yield from patch_google_storage()
