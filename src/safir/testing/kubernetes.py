"""Mock Kubernetes API for testing."""

from __future__ import annotations

import copy
import os
import re
import uuid
from typing import Any, Callable, Dict, Iterator, List, Optional
from unittest.mock import AsyncMock, Mock, patch

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import (
    ApiException,
    V1ConfigMap,
    V1Pod,
    V1PodList,
    V1PodStatus,
    V1Secret,
    V1Status,
)

__all__ = [
    "MockKubernetesApi",
    "patch_kubernetes",
]


class MockKubernetesApi:
    """Mock Kubernetes API for testing.

    This object simulates (with almost everything left out) the ``CoreV1Api``
    and ``CustomObjectApi`` client objects while keeping simple internal
    state.  It is intended to be used as a mock inside tests.

    Methods ending with ``_for_test`` are outside of the API and are intended
    for use by the test suite.

    If ``error_callback`` is set to a callable, it will be called with the
    method name and any arguments whenever any Kubernetes API method is called
    and before it takes any action.  This can be used to inject exceptions for
    test purposes.

    Notes
    -----
    This class is normally not instantiated directly.  Instead, call the
    `patch_kubernetes` function from a fixture to set up the mock.
    """

    def __init__(self) -> None:
        self.error_callback: Optional[Callable[..., None]] = None
        self.objects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.custom_kinds: Dict[str, str] = {}

    def get_all_objects_for_test(self, kind: str) -> List[Any]:
        """Return all objects of a given kind sorted by namespace and name.

        Parameters
        ----------
        kind : `str`
            The Kubernetes kind, such as ``Secret`` or ``Pod``.  This is
            case-sensitive.

        Returns
        -------
        objects : List[`typing.Any`]
            All objects of that kind found in the mock, sorted by namespace
            and then name.
        """
        key = self.custom_kinds[kind] if kind in self.custom_kinds else kind
        results = []
        for namespace in sorted(self.objects.keys()):
            if key not in self.objects[namespace]:
                continue
            for name in sorted(self.objects[namespace][key].keys()):
                results.append(self.objects[namespace][key][name])
        return results

    def _maybe_error(self, method: str, *args: Any) -> None:
        """Helper function to avoid using class method call syntax."""
        if self.error_callback:
            callback = self.error_callback
            callback(method, *args)

    def _get_object(self, namespace: str, key: str, name: str) -> Any:
        if namespace not in self.objects:
            reason = f"{namespace}/{name} not found"
            raise ApiException(status=404, reason=reason)
        if name not in self.objects[namespace].get(key, {}):
            reason = f"{namespace}/{name} not found"
            raise ApiException(status=404, reason=reason)
        return self.objects[namespace][key][name]

    def _store_object(
        self,
        namespace: str,
        key: str,
        name: str,
        obj: Any,
        replace: bool = False,
    ) -> None:
        if replace:
            self._get_object(namespace, key, name)
        else:
            if namespace not in self.objects:
                self.objects[namespace] = {}
            if key not in self.objects[namespace]:
                self.objects[namespace][key] = {}
            if name in self.objects[namespace][key]:
                msg = f"{namespace}/{name} exists"
                raise ApiException(status=500, reason=msg)
        self.objects[namespace][key][name] = obj

    def _delete_object(self, namespace: str, key: str, name: str) -> V1Status:
        self._get_object(namespace, key, name)
        del self.objects[namespace][key][name]
        return V1Status(code=200)

    # CUSTOM OBJECT API

    async def create_namespaced_custom_object(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        body: Dict[str, Any],
    ) -> None:
        self._maybe_error(
            "create_namespaced_custom_object",
            group,
            version,
            namespace,
            plural,
            body,
        )
        key = f"{group}/{version}/{plural}"
        if body["kind"] in self.custom_kinds:
            assert key == self.custom_kinds[body["kind"]]
        else:
            self.custom_kinds[body["kind"]] = key
        assert namespace == body["metadata"]["namespace"]
        obj = copy.deepcopy(body)
        obj["metadata"]["uid"] = str(uuid.uuid4())
        self._store_object(namespace, key, body["metadata"]["name"], obj)

    async def get_namespaced_custom_object(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        name: str,
    ) -> Dict[str, Any]:
        self._maybe_error(
            "get_namespaced_custom_object",
            group,
            version,
            namespace,
            plural,
            name,
        )
        return self._get_object(namespace, f"{group}/{version}/{plural}", name)

    async def list_cluster_custom_object(
        self, group: str, version: str, plural: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        self._maybe_error("list_cluster_custom_object", group, version, plural)
        key = f"{group}/{version}/{plural}"
        results = []
        for namespace in self.objects.keys():
            for name in self.objects[namespace].get(key, {}).keys():
                results.append(self.objects[namespace][key][name])
        return {"items": results}

    async def patch_namespaced_custom_object_status(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        name: str,
        body: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        self._maybe_error(
            "patch_namespaced_custom_object_status",
            group,
            version,
            namespace,
            plural,
            body,
        )
        key = f"{group}/{version}/{plural}"
        obj = copy.deepcopy(self._get_object(namespace, key, name))
        for change in body:
            assert change["op"] == "replace"
            assert change["path"] == "/status"
            obj["status"] = change["value"]
        self._store_object(namespace, key, name, obj, replace=True)
        return obj

    async def replace_namespaced_custom_object(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        name: str,
        body: Dict[str, Any],
    ) -> None:
        self._maybe_error(
            "replace_namespaced_custom_object",
            group,
            version,
            namespace,
            plural,
            name,
            body,
        )
        key = f"{group}/{version}/{plural}"
        assert key == self.custom_kinds[body["kind"]]
        assert namespace == body["metadata"]["namespace"]
        self._store_object(namespace, key, name, body, replace=True)

    # CONFIGMAP API

    async def create_namespaced_config_map(
        self, namespace: str, config_map: V1ConfigMap
    ) -> None:
        self._maybe_error(
            "create_namespaced_config_map", namespace, config_map
        )
        assert namespace == config_map.metadata.namespace
        name = config_map.metadata.name
        self._store_object(namespace, "ConfigMap", name, config_map)

    async def delete_namespaced_config_map(
        self, name: str, namespace: str
    ) -> V1Status:
        self._maybe_error("delete_namespaced_config_map", name, namespace)
        return self._delete_object(namespace, "ConfigMap", name)

    # POD API

    async def create_namespaced_pod(self, namespace: str, pod: V1Pod) -> None:
        self._maybe_error("create_namespaced_pod", namespace, pod)
        assert namespace == pod.metadata.namespace
        name = pod.metadata.name
        pod.status = V1PodStatus(phase="Running")
        self._store_object(namespace, "Pod", name, pod)

    async def delete_namespaced_pod(
        self, name: str, namespace: str
    ) -> V1Status:
        self._maybe_error("delete_namespaced_pod", name, namespace)
        return self._delete_object(namespace, "Pod", name)

    async def list_namespaced_pod(
        self, namespace: str, *, field_selector: str
    ) -> V1PodList:
        self._maybe_error("list_namespaced_pod", namespace, field_selector)
        match = re.match(r"metadata\.name=(.*)$", field_selector)
        assert match and match.group(1)
        pod = self._get_object(namespace, "Pod", match.group(1))
        return V1PodList(kind="Pod", items=[pod])

    async def read_namespaced_pod(self, name: str, namespace: str) -> V1Pod:
        self._maybe_error("read_namespaced_pod", name, namespace)
        return self._get_object(namespace, "Pod", name)

    # SECRETS API

    async def create_namespaced_secret(
        self, namespace: str, secret: V1Secret
    ) -> None:
        self._maybe_error("create_namespaced_secret", namespace, secret)
        assert namespace == secret.metadata.namespace
        self._store_object(namespace, "Secret", secret.metadata.name, secret)

    async def patch_namespaced_secret(
        self, name: str, namespace: str, body: List[Dict[str, Any]]
    ) -> V1Secret:
        self._maybe_error("patch_namespaced_secret", name, namespace)
        obj = copy.deepcopy(self._get_object(namespace, "Secret", name))
        for change in body:
            assert change["op"] == "replace"
            if change["path"] == "/metadata/annotations":
                obj.metadata.annotations = change["value"]
            elif change["path"] == "/metadata/labels":
                obj.metadata.labels = change["value"]
            else:
                assert False, f'unsupported path {change["path"]}'
        self._store_object(namespace, "Secret", name, obj, replace=True)

    async def read_namespaced_secret(
        self, name: str, namespace: str
    ) -> V1Secret:
        self._maybe_error("read_namespaced_secret", name, namespace)
        return self._get_object(namespace, "Secret", name)

    async def replace_namespaced_secret(
        self, name: str, namespace: str, secret: V1Secret
    ) -> None:
        self._maybe_error("replace_namespaced_secret", namespace, secret)
        self._store_object(namespace, "Secret", name, secret, replace=True)


def patch_kubernetes() -> Iterator[MockKubernetesApi]:
    """Replace the Kubernetes API with a mock class.

    Returns
    -------
    mock_kubernetes : `MockKubernetesApi`
        The mock Kubernetes API object.

    Notes
    -----
    This function will mock out the Kuberentes library configuration API in a
    manner compatible with `safir.kubernetes.initialize_kubernetes`, ensuring
    that it does nothing during test.  It will replace the Kubernetes
    ``ApiClient`` object with a `~unittest.mock.MagicMock` and then redirect
    ``CoreV1Api`` and ``CustomObjectsApi`` to a `MockKubernetesApi` instance.

    To use this mock successfully, you must not import ``ApiClient``,
    ``CoreV1Api``, or ``CustomObjectsApi`` directly into the local namespace,
    or they will not be correctly patched.  Instead, use:

    .. code-block:: python

       from kubernetes_asyncio import client

    and then use ``client.ApiClient`` and so forth.

    Examples
    --------
    Normally this should be called from a fixture in ``tests/conftest.py``
    such as the following:

    .. code-block:: python

       from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes


       @pytest.fixture
       def mock_kubernetes() -> Iterator[MockKubernetesApi]:
           yield from patch_kubernetes()
    """
    mock_api = MockKubernetesApi()
    with patch.object(config, "load_incluster_config"):
        patchers = []
        for api in ("CoreV1Api", "CustomObjectsApi"):
            patcher = patch.object(client, api)
            mock_class = patcher.start()
            mock_class.return_value = mock_api
            patchers.append(patcher)
        with patch.object(client, "ApiClient") as mock_client:
            mock_client.return_value = Mock(spec=client.ApiClient)
            mock_client.return_value.close = AsyncMock()
            os.environ["KUBERNETES_PORT"] = "tcp://10.0.0.1:443"
            yield mock_api
            del os.environ["KUBERNETES_PORT"]
        for patcher in patchers:
            patcher.stop()
