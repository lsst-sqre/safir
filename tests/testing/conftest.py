"""Fixtures for tests of the testing support infrastructure.

Defines fixtures similar to what users of the Safir library should define so
that they can be exercised in tests of the test support infrastructure.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Iterator

import pytest

from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes


@pytest.fixture
def mock_kubernetes() -> Iterator[MockKubernetesApi]:
    yield from patch_kubernetes()


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
