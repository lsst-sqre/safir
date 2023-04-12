"""Tests for Kubernetes utilities."""

from __future__ import annotations

import pytest
from kubernetes_asyncio import config

from safir.kubernetes import initialize_kubernetes
from safir.testing.kubernetes import MockKubernetesApi


@pytest.mark.asyncio
async def test_initialize(mock_kubernetes: MockKubernetesApi) -> None:
    await initialize_kubernetes()
    assert config.load_incluster_config.call_count == 1
