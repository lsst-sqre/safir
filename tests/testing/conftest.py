"""Fixtures for tests of the testing support infrastructure.

Defines fixtures similar to what users of the Safir library should define so
that they can be exercised in tests of the test support infrastructure.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes


@pytest.fixture
def mock_kubernetes() -> Iterator[MockKubernetesApi]:
    yield from patch_kubernetes()
