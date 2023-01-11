"""Test fixtures."""

from __future__ import annotations

from datetime import timedelta
from typing import Iterator

import pytest

from safir.testing.gcs import MockStorageClient, patch_google_storage


@pytest.fixture
def mock_gcs() -> Iterator[MockStorageClient]:
    yield from patch_google_storage(
        expected_expiration=timedelta(hours=1), bucket_name="some-bucket"
    )
