"""Tests for the Kubernetes support infrastructure.

These are just basic sanity checks that the mocking is working correctly and
the basic calls work.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import ANY

import pytest
from kubernetes_asyncio import config
from kubernetes_asyncio.client import V1ObjectMeta, V1Secret

from safir.kubernetes import initialize_kubernetes
from safir.testing.kubernetes import MockKubernetesApi


@pytest.mark.asyncio
async def test_initialize(mock_kubernetes: MockKubernetesApi) -> None:
    await initialize_kubernetes()
    assert config.load_incluster_config.call_count == 1


@pytest.mark.asyncio
async def test_mock(mock_kubernetes: MockKubernetesApi) -> None:
    custom: Dict[str, Any] = {
        "apiVersion": "gafaelfawr.lsst.io/v1alpha1",
        "kind": "GafaelfawrServiceToken",
        "metadata": {
            "name": "gafaelfawr-secret",
            "namespace": "mobu",
            "generation": 1,
        },
        "spec": {
            "service": "mobu",
            "scopes": ["admin:token"],
        },
    }
    secret = V1Secret(
        api_version="v1",
        kind="Secret",
        data={"token": "bogus"},
        metadata=V1ObjectMeta(name="gafaelfawr-secret", namespace="mobu"),
        type="Opaque",
    )
    await mock_kubernetes.create_namespaced_custom_object(
        "gafaelfawr.lsst.io",
        "v1alpha1",
        custom["metadata"]["namespace"],
        "gafaelfawrservicetokens",
        custom,
    )
    await mock_kubernetes.create_namespaced_secret(
        secret.metadata.namespace, secret
    )

    assert await mock_kubernetes.list_cluster_custom_object(
        "gafaelfawr.lsst.io", "v1alpha1", "gafaelfawrservicetokens"
    ) == {
        "items": [{**custom, "metadata": {**custom["metadata"], "uid": ANY}}]
    }
    assert mock_kubernetes.get_all_objects_for_test("Secret") == [secret]

    def error(method: str, *args: Any) -> None:
        assert method == "replace_namespaced_custom_object"
        raise ValueError("some exception")

    mock_kubernetes.error_callback = error
    with pytest.raises(ValueError) as excinfo:
        await mock_kubernetes.replace_namespaced_custom_object(
            "gafaelfawr.lsst.io",
            "v1alpha1",
            custom["metadata"]["namespace"],
            "gafaelfawrservicetokens",
            "gafaelfawr-secret",
            custom,
        )
    assert str(excinfo.value) == "some exception"
