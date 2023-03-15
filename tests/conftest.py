"""Test fixtures."""

from __future__ import annotations

from datetime import timedelta
from typing import Iterator

import pytest
import respx

from safir.testing.gcs import MockStorageClient, patch_google_storage
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook


@pytest.fixture
def mock_gcs() -> Iterator[MockStorageClient]:
    yield from patch_google_storage(
        expected_expiration=timedelta(hours=1), bucket_name="some-bucket"
    )


@pytest.fixture
def mock_slack(respx_mock: respx.Router) -> MockSlackWebhook:
    return mock_slack_webhook("https://example.com/slack", respx_mock)
