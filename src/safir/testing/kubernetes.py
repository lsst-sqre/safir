"""Mock Kubernetes API for testing."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import timedelta
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock, patch

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import (
    ApiException,
    CoreV1Event,
    CoreV1EventList,
    V1ConfigMap,
    V1DeleteOptions,
    V1Ingress,
    V1IngressList,
    V1IngressStatus,
    V1Job,
    V1JobList,
    V1JobStatus,
    V1LoadBalancerStatus,
    V1Namespace,
    V1NamespaceList,
    V1NetworkPolicy,
    V1Node,
    V1NodeList,
    V1ObjectMeta,
    V1ObjectReference,
    V1PersistentVolumeClaim,
    V1Pod,
    V1PodList,
    V1PodStatus,
    V1ResourceQuota,
    V1Secret,
    V1Service,
    V1ServiceList,
    V1Status,
)

from ..datetime import current_datetime

__all__ = [
    "MockKubernetesApi",
    "patch_kubernetes",
    "strip_none",
]


def _parse_label_selector(label_selector: str) -> dict[str, str]:
    """Parse a label selector.

    Only equality is supported (with ``=`` or ``==``).

    Parameters
    ----------
    label_selector
        Label selector string to parse.

    Returns
    -------
    dict of str to str
        Dictionary of required labels to their required values.

    Raises
    ------
    AssertionError
        Raised if the label selector string is not a supported syntax.
    """
    result = {}
    for requirement in label_selector.split(","):
        match = re.match(r"([^!=]+)==?(.*)", requirement)
        assert match and match.group(1) and match.group(2)
        result[match.group(1)] = match.group(2)
    return result


def _check_labels(
    obj_labels: Optional[dict[str, str]], label_selector: Optional[str]
) -> bool:
    """Check whether an object's labels match the label selector supplied.

    Parameters
    ----------
    obj_labels
        Kubernetes object labels

    label_selector
        label selector in string form

    Returns
    -------
    bool
        Did all of the supplied label_selector labels match
        the object labels?
    """
    if label_selector is None or label_selector == "":
        # Everything matches the absence of a selector.
        return True
    if obj_labels is None or not obj_labels:
        # If there are no labels but a non-empty selector, it doesn't
        # match.
        return False
    labels = _parse_label_selector(label_selector)
    for lbl in labels:
        if lbl not in obj_labels or labels[lbl] != obj_labels[lbl]:
            # Label isn't present or its value isn't right
            return False
    # The whole selector is correct.
    return True


def strip_none(model: dict[str, Any]) -> dict[str, Any]:
    """Strip `None` values from a serialized Kubernetes object.

    Comparing Kubernetes objects against serialized expected output is a bit
    of a pain, since Kubernetes objects often contain tons of optional
    parameters and the ``to_dict`` serialization includes every parameter.
    The naive result is therefore tedious to read or understand.

    This function works around this by taking a serialized Kubernetes object
    and dropping all of the parameters that are set to `None`. The ``to_dict``
    form of a Kubernetes object should be passed through it first before
    comparing to the expected output.

    Parmaters
    ---------
    model
        Kubernetes model serialized with ``to_dict``.

    Returns
    -------
    dict
        Cleaned-up model with `None` parameters removed.
    """
    result = {}
    for key, value in model.items():
        if value is None:
            continue
        if isinstance(value, dict):
            value = strip_none(value)
        elif isinstance(value, list):
            list_result = []
            for item in value:
                if isinstance(item, dict):
                    item = strip_none(item)
                list_result.append(item)
            value = list_result
        result[key] = value
    return result


class _EventStream:
    """Holds the data for a stream of watchable events.

    This is an internal implementation detail of the Kubernetes mock. It holds
    a stream of watchable events and a list of `asyncio.Event` triggers. A
    watch can register interest in this event stream, in which case its
    trigger will be notified when anything new is added to the event stream.
    The events are generic dicts, which will be interpreted by the Kubernetes
    library differently depending on which underlying API is using this data
    structure.
    """

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._triggers: list[asyncio.Event] = []

    @property
    def next_resource_version(self) -> str:
        """Resource version of the next event.

        This starts with ``1`` to ensure that a resource version of ``0`` is
        special and means to return all known events, so it must be adjusted
        when indexing into a list of events.
        """
        return str(len(self._events) + 1)

    def add_event(self, event: dict[str, Any]) -> None:
        """Add a new event and notify all watchers.

        Parameters
        ----------
        event
            New event.
        """
        self._events.append(event)
        for trigger in self._triggers:
            trigger.set()

    def build_watch_response(
        self,
        resource_version: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        *,
        field_selector: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> Mock:
        """Construct a response to a watch request.

        Wraps a watch iterator in the appropriate mock to behave as expected
        when called from ``kubernetes_asyncio``. This simulates an aiohttp
        response.

        Parameters
        ----------
        resource_version
            Starting resource version for the watch. The resource versions
            must be the position in the events stream, stringified.
        timeout_seconds
            How long to watch. This is total elapsed time, not the time
            between events. It matches the corresponding parameter in the
            Kubernetes API. If `None`, watch forever.
        field_selector
            Which events to retrieve when performing a watch. If set, it must
            be set to ``metadata.name=...`` to match a specific object name.

        Returns
        -------
        Mock
            Simulation of an aiohttp response whose ``readline`` method wraps
            the iterator.

        Raises
        ------
        AssertionError
            Some other ``field_selector`` was provided.
        """
        generator = self._build_watcher(
            resource_version, timeout_seconds, field_selector, label_selector
        )

        async def readline() -> bytes:
            return await generator.__anext__()

        response = Mock()
        response.content.readline = AsyncMock()
        response.content.readline.side_effect = readline
        return response

    def _build_watcher(
        self,
        resource_version: str | None,
        timeout_seconds: int | None,
        field_selector: str | None,
        label_selector: str | None,
    ) -> AsyncIterator[bytes]:
        """Construct a watcher for this event stream.

        Parameters
        ----------
        resource_version
            Starting resource version for the watch. The resource version
            must be the position in the events stream, stringified. If not
            given, start after the most recent event.
        timeout_seconds
            How long to watch. This is total elapsed time, not the time
            between events. It matches the corresponding parameter in the
            Kubernetes API. If `None`, watch forever.
        field_selector
            Which events to retrieve when performing a watch. If set, it must
            be set to ``metadata.name=...`` to match a specific object name.
        label_selector
            Which events to retrieve when performing a watch.  All
            labels must match.

        Returns
        -------
        AsyncIterator
            An async iterator that will return each new event in the stream,
            encoded as expected by the Kubernetes API, until the timeout
            occurs.

        Raises
        ------
        AssertionError
            Some other ``field_selector`` was provided.
        """
        timeout = None
        if timeout_seconds is not None:
            timeout = current_datetime() + timedelta(seconds=timeout_seconds)

        # Parse the field selector, if one was provided.
        name = None
        if field_selector:
            match = re.match(r"metadata\.name=(.*)$", field_selector)
            assert match and match.group(1)
            name = match.group(1)

        # Create and register a new trigger.
        trigger = asyncio.Event()
        self._triggers.append(trigger)

        # Construct the iterator.
        async def next_event() -> AsyncIterator[bytes]:
            if resource_version:
                position = int(resource_version)
            else:
                position = len(self._events)
            while True:
                for event in self._events[position:]:
                    position += 1
                    if name and event["object"]["metadata"]["name"] != name:
                        continue
                    if not _check_labels(
                        event["object"]["metadata"]["labels"], label_selector
                    ):
                        continue
                    yield json.dumps(event).encode()
                if not timeout:
                    await trigger.wait()
                else:
                    now = current_datetime()
                    timeout_left = (timeout - now).total_seconds()
                    if timeout_left <= 0:
                        yield b""
                        break
                    try:
                        async with asyncio.timeout(timeout_left):
                            await trigger.wait()
                    except TimeoutError:
                        yield b""
                        break
                trigger.clear()
            self._triggers = [t for t in self._triggers if t != trigger]

        # Return the iterator.
        return next_event()


class MockKubernetesApi:
    """Mock Kubernetes API for testing.

    This object simulates (with almost everything left out) the ``BatchV1Api``,
    ``CoreV1Api``, ``CustomObjectApi``, and ``NetworkingV1Api`` client
    objects while keeping simple internal state. It is intended to be used
    as a mock inside tests.

    Methods ending with ``_for_test`` are outside of the API and are intended
    for use by the test suite.

    This mock does not enforce namespace creation before creating objects in a
    namespace. Creating an object in a namespace will implicitly create that
    namespace if it doesn't exist. However, it will not store a
    ``V1Namespace`` object, so to verify that a namespace was properly created
    (although not the order of creation), retrieve all the objects in the
    namespace with `get_namespace_objects_for_test` and one of them will be
    the ``V1Namespace`` object.

    Objects stored with ``create_*`` or ``replace_*`` methods are **NOT**
    copied. The object provided will be stored, so changing that object will
    change the object returned by subsequent API calls. Likewise, the object
    returned by ``read_*`` calls will be the same object stored in the mock,
    and changing it will change the mock's data. (Sometimes this is the
    desired behavior, sometimes it isn't; we had to pick one and this is the
    approach we picked.)

    Most APIs do not support watches. The current exceptions are
    `list_namespaced_event`, `list_namespaced_ingress`, `list_namespaced_job`,
    `list_namespaced_pod`, and `list_namespaced_service`.

    Attributes
    ----------
    initial_pod_phase
        String value to set the status of pods to when created. If this is set
        to ``Running`` (the default), a pod start event will also be
        generated when the pod is created.
    error_callback
        If set, called with the method name and any arguments whenever any
        Kubernetes API method is called and before it takes any acttion. This
        can be used for fault injection for testing purposes.

    Notes
    -----
    This class is normally not instantiated directly. Instead, call the
    `patch_kubernetes` function from a fixture to set up the mock. This is
    also why it is configurable by setting attributes rather than constructor
    arguments; the individual test usually doesn't have control of the
    constructor.
    """

    def __init__(self) -> None:
        self.error_callback: Optional[Callable[..., None]] = None
        self.initial_pod_phase = "Running"

        self._custom_kinds: dict[str, str] = {}
        self._nodes = V1NodeList(items=[])
        self._objects: dict[str, dict[str, dict[str, Any]]] = {}
        self._events: defaultdict[str, list[CoreV1Event]] = defaultdict(list)
        self._event_streams: defaultdict[str, dict[str, _EventStream]]
        self._event_streams = defaultdict(lambda: defaultdict(_EventStream))

    def get_all_objects_for_test(self, kind: str) -> list[Any]:
        """Return all objects of a given kind sorted by namespace and name.

        Parameters
        ----------
        kind
            The Kubernetes kind, such as ``Secret`` or ``Pod``. This is
            case-sensitive.

        Returns
        -------
        list of Any
            All objects of that kind found in the mock, sorted by namespace
            and then name.
        """
        key = self._custom_kinds[kind] if kind in self._custom_kinds else kind
        results = []
        for namespace in sorted(self._objects.keys()):
            if key not in self._objects[namespace]:
                continue
            for name, obj in sorted(self._objects[namespace][key].items()):
                results.append(obj)
        return results

    def get_namespace_objects_for_test(self, namespace: str) -> list[Any]:
        """Returns all objects in the given namespace.

        Parameters
        ----------
        namespace
            Name of the namespace.

        Returns
        -------
        list of Any
            All objects found in that namespace, sorted by kind and then name.
            Due to how objects are stored in the mock, we can't distinguish
            between a missing namespace and a namespace with no objects. In
            both cases, the empty list is returned.
        """
        if namespace not in self._objects:
            return []
        result = []
        for kind in sorted(self._objects[namespace].keys()):
            for _, body in sorted(self._objects[namespace][kind].items()):
                result.append(body)
        return result

    def set_nodes_for_test(self, nodes: list[V1Node]) -> None:
        """Set the node structures that will be returned by `list_node`.

        Parameters
        ----------
        nodes
            New node list to return.
        """
        self._nodes = V1NodeList(items=nodes)

    # CUSTOM OBJECT API

    async def create_namespaced_custom_object(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        body: dict[str, Any],
    ) -> None:
        """Create a new custom namespaced object.

        Parameters
        ----------
        group
            API group for this custom object.
        version
            API version for this custom object.
        namespace
            Namespace in which to create the object.
        plural
            API plural for this custom object.
        body
            Custom object to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error(
            "create_namespaced_custom_object",
            group,
            version,
            namespace,
            plural,
            body,
        )
        api_version = body.get("api_version", body["apiVersion"])
        assert api_version == f"{group}/{version}"
        key = f"{group}/{version}/{plural}"
        if body["kind"] in self._custom_kinds:
            assert key == self._custom_kinds[body["kind"]]
        else:
            self._custom_kinds[body["kind"]] = key
        assert namespace == body["metadata"]["namespace"]
        self._store_object(namespace, key, body["metadata"]["name"], body)

    async def delete_namespaced_custom_object(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        name: str,
        *,
        grace_period_seconds: int | None = None,
        body: V1DeleteOptions | None = None,
    ) -> Any:
        """Delete a custom namespaced object.

        Parameters
        ----------
        group
            API group for this custom object.
        version
            API version for this custom object.
        namespace
            Namespace in which to delete the object.
        plural
            API plural for this custom object.
        name
            Custom object to delete.
        grace_period_seconds
            Grace period for object deletion (currently ignored).
        body
            Delete options (currently ignored).

        Returns
        -------
        kubernetes_asyncio.client.V1Status
            Success status if object was deleted.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error("delete_namespaced_custom_object", name, namespace)
        key = f"{group}/{version}/{plural}"
        return self._delete_object(namespace, key, name)

    async def get_namespaced_custom_object(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        name: str,
    ) -> dict[str, Any]:
        """Retrieve a namespaced custom object.

        Parameters
        ----------
        group
            API group for this custom object.
        version
            API version for this custom object.
        namespace
            Namespace in which to create the object.
        plural
            API plural for this custom object.
        name
            Name of the object to retrieve.

        Returns
        -------
        dict of Any
            Body of the custom object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the object does not exist.
        """
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
    ) -> dict[str, list[dict[str, Any]]]:
        """List all custom objects in the cluster.

        Parameters
        ----------
        group
            API group for this custom object.
        version
            API version for this custom object.
        plural
            API plural for this custom object.

        Returns
        -------
        dict
            Dictionary with one key, ``items``, whose value is a list of all
            the specified custom objects stored in the cluster.
        """
        self._maybe_error("list_cluster_custom_object", group, version, plural)
        key = f"{group}/{version}/{plural}"
        results = []
        for namespace in self._objects.keys():
            for name, obj in self._objects[namespace].get(key, {}).items():
                results.append(obj)
        return {"items": results}

    async def patch_namespaced_custom_object_status(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        name: str,
        body: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Patch the status of a namespaced custom object.

        Parameters
        ----------
        group
            API group for this custom object.
        version
            API version for this custom object.
        namespace
            Namespace in which to create the object.
        plural
            API plural for this custom object.
        name
            Name of the object to retrieve.
        body
            Body of the patch. The only patch supported is one with ``op`` of
            ``replace`` and ``path`` of ``/status``.

        Returns
        -------
        dict of Any
            Modified body of the custom object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the object does not exist.
        AssertionError
            Raised if any other type of patch is provided.
        """
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
        body: dict[str, Any],
    ) -> None:
        """Replace a custom namespaced object.

        Parameters
        ----------
        group
            API group for this custom object.
        version
            API version for this custom object.
        namespace
            Namespace in which to create the object.
        plural
            API plural for this custom object.
        body
            New contents of custom object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 if the object does not exist.
        """
        self._maybe_error(
            "replace_namespaced_custom_object",
            group,
            version,
            namespace,
            plural,
            name,
            body,
        )
        api_version = body.get("api_version", body["apiVersion"])
        assert api_version == f"{group}/{version}"
        key = f"{group}/{version}/{plural}"
        assert key == self._custom_kinds[body["kind"]]
        assert namespace == body["metadata"]["namespace"]
        self._store_object(namespace, key, name, body, replace=True)

    # CONFIGMAP API

    async def create_namespaced_config_map(
        self, namespace: str, body: V1ConfigMap
    ) -> None:
        """Create a ``ConfigMap`` object.

        Parameters
        ----------
        namespace
            Namespace in which to store the object.
        body
            Object to store.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error("create_namespaced_config_map", namespace, body)
        self._update_metadata(body, "v1", "ConfigMap", namespace)
        name = body.metadata.name
        self._store_object(namespace, "ConfigMap", name, body)

    async def delete_namespaced_config_map(
        self,
        name: str,
        namespace: str,
        *,
        grace_period_seconds: int | None = None,
        body: V1DeleteOptions | None = None,
    ) -> V1Status:
        """Delete a ``ConfigMap`` object.

        Parameters
        ----------
        name
            Name of object.
        namespace
            Namespace of object.
        grace_period_seconds
            Grace period for object deletion (currently ignored).
        body
            Delete options (currently ignored).

        Returns
        -------
        kubernetes_asyncio.client.V1Status
            Success status if object was deleted.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the object does not exist.
        """
        self._maybe_error("delete_namespaced_config_map", name, namespace)
        return self._delete_object(namespace, "ConfigMap", name)

    async def read_namespaced_config_map(
        self, name: str, namespace: str
    ) -> V1ConfigMap:
        """Read a config map object.

        Parameters
        ----------
        name
            Name of object.
        namespace
            Namespace of object.

        Returns
        -------
        kubernetes_asyncio.client.V1ConfigMap
            Corresponding object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the config map was not found.
        """
        self._maybe_error("read_namespaced_config_map", name, namespace)
        return self._get_object(namespace, "ConfigMap", name)

    # EVENTS API

    async def create_namespaced_event(
        self, namespace: str, body: CoreV1Event
    ) -> None:
        """Store a new namespaced event.

        This uses the old core event API, not the new Events API.

        Parameters
        ----------
        namespace
            Namespace of the event.
        body
            New event to store.
        """
        self._maybe_error("create_namespaced_event", namespace, body)
        self._update_metadata(body, "v1", "Event", namespace)
        stream = self._event_streams[namespace]["Event"]
        body.metadata.resource_version = stream.next_resource_version
        stream.add_event({"type": "ADDED", "object": body.to_dict()})
        self._events[namespace].append(body)

    async def list_namespaced_event(
        self,
        namespace: str,
        *,
        field_selector: Optional[str] = None,
        resource_version: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: Optional[int] = None,
    ) -> CoreV1EventList | Mock:
        """List namespaced events.

        This uses the old core event API, not the new Events API. It does
        support watches.

        Parameters
        ----------
        namespace
            Namespace to watch for events.
        field_selector
            Which events to retrieve when performing a watch. Currently, this
            is ignored.
        resource_version
            Where to start in the event stream when performing a watch.
        timeout_seconds
            How long to return events for before exiting when performing a
            watch.
        watch
            Whether to act as a watch.
        _preload_content
            Verified to be `False` when performing a watch.
        _request_timeout
            Ignored, accepted for compatibility with the watch API.

        Returns
        -------
        kubernetes_asyncio.client.CoreV1EventList or unittest.mock.Mock
            List of events, when not called as a watch. If called as a watch,
            returns a mock ``aiohttp.Response`` with a ``readline`` method
            that yields the events.
        """
        self._maybe_error("list_namespaced_event", namespace)
        if not watch:
            return CoreV1EventList(items=self._events[namespace])

        # All watches must not preload content since we're returning raw JSON.
        # This is done by the Kubernetes API Watch object.
        assert not _preload_content

        # Return the mock response expected by the Kubernetes API.
        stream = self._event_streams[namespace]["Event"]
        return stream.build_watch_response(resource_version, timeout_seconds)

    # INGRESS API

    async def create_namespaced_ingress(
        self, namespace: str, body: V1Ingress
    ) -> None:
        """Create an ingress object.

        In real life, it usually takes some time for the Ingress controller
        to set the ``status.load_balancer.ingress`` field.  It appears that
        status.load_balancer is created when the Ingress is but is empty,
        so that's what we do too.

        Use ``patch_namespaced_ingress_status()`` to update the field to
        indicate that the ingress is ready.

        Parameters
        ----------
        namespace
            Namespace in which to create the object.
        body
            Object to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error("create_namespaced_ingress", namespace, body)
        self._update_metadata(
            body, "networking.k8s.io/v1", "Ingress", namespace
        )
        name = body.metadata.name
        body.status = V1IngressStatus(
            load_balancer=V1LoadBalancerStatus(ingress=[])
        )
        self._store_object(namespace, "Ingress", name, body)
        stream = self._event_streams[namespace]["Ingress"]
        stream.add_event({"type": "ADDED", "object": body.to_dict()})

    async def delete_namespaced_ingress(
        self,
        name: str,
        namespace: str,
        *,
        grace_period_seconds: int | None = None,
        body: V1DeleteOptions | None = None,
    ) -> V1Status:
        """Delete an ingress object.

        Parameters
        ----------
        name
            Name of ingress to delete.
        namespace
            Namespace of ingress to delete.
        grace_period_seconds
            Grace period for object deletion (currently ignored).
        body
            Delete options (currently ignored).

        Returns
        -------
        kubernetes_asyncio.client.V1Status
            Success status.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the ingress was not found.
        """
        self._maybe_error("delete_namespaced_ingress", name, namespace)
        ingress = self._get_object(namespace, "Ingress", name)
        stream = self._event_streams[namespace]["Ingress"]
        stream.add_event({"type": "DELETED", "object": ingress.to_dict()})
        return self._delete_object(namespace, "Ingress", name)

    async def read_namespaced_ingress(
        self, name: str, namespace: str
    ) -> V1Ingress:
        """Read a ingress object.

        Parameters
        ----------
        name
            Name of the ingress.
        namespace
            Namespace of the ingress.

        Returns
        -------
        kubernetes_asyncio.client.V1Ingress
            Ingress object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the ingress was not found.
        """
        self._maybe_error("read_namespaced_ingress", name, namespace)
        return self._get_object(namespace, "Ingress", name)

    async def list_namespaced_ingress(
        self,
        namespace: str,
        *,
        field_selector: Optional[str] = None,
        label_selector: Optional[str] = None,
        resource_version: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: Optional[int] = None,
    ) -> V1IngressList | Mock:
        """List ingress objects in a namespace.

        This does support watches.

        Parameters
        ----------
        namespace
            Namespace of ingresss to list.
        field_selector
            Only ``metadata.name=...`` is supported. It is parsed to find the
            ingress name and only ingresss matching that name will be returned.
        label_selector
            Which events to retrieve when performing a watch.  All
            labels must match.
        resource_version
            Where to start in the event stream when performing a watch. If
            `None`, starts with the next change.
        timeout_seconds
            How long to return events for before exiting when performing a
            watch.
        watch
            Whether to act as a watch.
        _preload_content
            Verified to be `False` when performing a watch.
        _request_timeout
            Ignored, accepted for compatibility with the watch API.

        Returns
        -------
        kubernetes_asyncio.client.V1IngressList or unittest.mock.Mock
            List of ingresss in that namespace, when not called as a watch. If
            called as a watch, returns a mock ``aiohttp.Response`` with a
            ``readline`` metehod that yields the events.

        Raises
        ------
        AssertionError
            Some other ``field_selector`` was provided.
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error("list_namespaced_ingress", namespace, field_selector)
        if namespace not in self._objects:
            msg = f"Namespace {namespace} not found"
            raise ApiException(status=404, reason=msg)
        if not watch:
            if field_selector:
                match = re.match(r"metadata\.name=(.*)$", field_selector)
                assert match and match.group(1)
                try:
                    ingress = self._get_object(
                        namespace, "Ingress", match.group(1)
                    )
                    return V1IngressList(kind="Ingress", items=[ingress])
                except ApiException:
                    return V1IngressList(kind="Ingress", items=[])
            else:
                ingresss = []
                if "Ingress" in self._objects[namespace]:
                    for obj in self._objects[namespace]["Ingress"].values():
                        if _check_labels(obj.metadata.labels, label_selector):
                            ingresss.append(obj)
                return V1IngressList(kind="Ingress", items=ingresss)

        # All watches must not preload content since we're returning raw JSON.
        # This is done by the Kubernetes API Watch object.
        assert not _preload_content

        # Return the mock response expected by the Kubernetes API.
        stream = self._event_streams[namespace]["Ingress"]
        return stream.build_watch_response(
            resource_version,
            timeout_seconds,
            field_selector=field_selector,
            label_selector=label_selector,
        )

    async def patch_namespaced_ingress_status(
        self, name: str, namespace: str, body: list[dict[str, Any]]
    ) -> V1Secret:
        """Patch the status of an ingress object.

        Parameters
        ----------
        name
            Name of ingress object.
        namespace
            Namespace of ingress object.
        body
            Patches to apply. Only patches with ``op`` of ``replace`` are
            supported, and only with ``path`` of
            ``/status/loadBalancer/ingress``.

        Returns
        -------
        kubernetes_asyncio.client.V1Ingress
            Corresponding object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the ingress does not exist.
        AssertionError
            Raised if any other type of patch was provided.
        """
        self._maybe_error("patch_namespaced_ingress", name, namespace)
        ingress = copy.deepcopy(self._get_object(namespace, "Ingress", name))
        for change in body:
            assert change["op"] == "replace"
            assert change["path"] == "/status/loadBalancer/ingress"
            ingress.status.load_balancer.ingress = change["value"]
        stream = self._event_streams[namespace]["Ingress"]
        ingress.metadata.resource_version = stream.next_resource_version
        self._store_object(namespace, "Ingress", name, ingress, replace=True)
        stream.add_event({"type": "MODIFIED", "object": ingress.to_dict()})
        return ingress

    # JOB API

    async def create_namespaced_job(self, namespace: str, body: V1Job) -> None:
        """Create a job object.

        A pod corresponding to this job will also be created. The pod will
        have a label ``job-name`` set to the name of the Job object. Its
        name will be the job's name prepended to ``-abcde``. If
        ``initial_pod_phase`` on the mock is set to ``Running``, the
        ``status.active`` field of the job will be set to 1.

        Parameters
        ----------
        namespace
            Namespace in which to create the object.
        body
            Object to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error("create_namespaced_job", namespace, body)
        self._update_metadata(body, "batch/v1", "Job", namespace)
        name = body.metadata.name
        self._store_object(namespace, "Job", name, body)
        # Pretend to spawn a pod
        # If there is no metadata, create a V1ObjectMeta object with just
        # namespace, a "generateName" of the job name, and a "job-name"
        # label, which appears to be what Kubernetes does.
        template = body.spec.template
        podmd = template.metadata
        if podmd is None:
            podmd = V1ObjectMeta(
                namespace=namespace,
                generate_name=f"{name}-",
            )
        # In real life, the name has five random alphanumeric characters,
        # but for testing we'd like to know what the spawned pod is going to
        # be called.  But in real life, if you set "generateName" you can't
        # also set the pod name.
        podmd.name = name + "-abcde"
        podmd.labels["job-name"] = name
        pod = V1Pod(metadata=podmd, spec=template.spec)
        await self.create_namespaced_pod(namespace, pod)
        if pod.status.phase == "Running":
            body.status = V1JobStatus(active=1)

    async def delete_namespaced_job(
        self,
        name: str,
        namespace: str,
        *,
        grace_period_seconds: int | None = None,
        propagation_policy: str = "Foreground",
        body: V1DeleteOptions | None = None,
    ) -> V1Status:
        """Delete a job object.

        Will also propagate to pods.

        Parameters
        ----------
        name
            Name of job to delete.
        namespace
            Namespace of job to delete.
        grace_period_seconds
            Grace period for object deletion (currently ignored).
        propagation_policy
            Propagation policy for deletion. Must be ``Foreground`` if
            specified, and has no effect on the behavior of the mock.
        body
            Delete options (currently ignored).

        Returns
        -------
        kubernetes_asyncio.client.V1Status
            Success status.

        Raises
        ------
        AssertionError
            Raised if the propagation policy is not ``Foreground``.
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the job was not found.
        """
        if propagation_policy not in ("Foreground", "Background", "Orphan"):
            msg = f"Invalid propagation_policy {propagation_policy}"
            raise AssertionError(msg)
        self._maybe_error("delete_namespaced_job", name, namespace)

        # This simulates a foreground deletion, where the Job is blocked
        # from deletion until all its pods are deleted. We also use it for
        # background deletion for the time being, since it should be close
        # enough.
        pods = await self.list_namespaced_pod(
            namespace, label_selector=f"job-name=={name}"
        )
        if propagation_policy != "Orphan":
            for pod in pods.items:
                await self.delete_namespaced_pod(pod.metadata.name, namespace)

        job = self._get_object(namespace, "Job", name)
        stream = self._event_streams[namespace]["Job"]
        stream.add_event({"type": "DELETED", "object": job.to_dict()})
        return self._delete_object(namespace, "Job", name)

    async def list_namespaced_job(
        self,
        namespace: str,
        *,
        field_selector: Optional[str] = None,
        label_selector: Optional[str] = None,
        resource_version: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: Optional[int] = None,
    ) -> V1JobList | Mock:
        """List job objects in a namespace.

        This does support watches.

        Parameters
        ----------
        namespace
            Namespace of jobs to list.
        field_selector
            Only ``metadata.name=...`` is supported. It is parsed to find the
            job name and only jobs matching that name will be returned.
        label_selector
            Which events to retrieve when performing a watch.  All
            labels must match.
        resource_version
            Where to start in the event stream when performing a watch. If
            `None`, starts with the next change.
        timeout_seconds
            How long to return events for before exiting when performing a
            watch.
        watch
            Whether to act as a watch.
        _preload_content
            Verified to be `False` when performing a watch.
        _request_timeout
            Ignored, accepted for compatibility with the watch API.

        Returns
        -------
        kubernetes_asyncio.client.V1JobList or unittest.mock.Mock
            List of jobs in that namespace, when not called as a watch. If
            called as a watch, returns a mock ``aiohttp.Response`` with a
            ``readline`` metehod that yields the events.

        Raises
        ------
        AssertionError
            Some other ``field_selector`` was provided.
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error("list_namespaced_job", namespace, field_selector)
        if namespace not in self._objects:
            msg = f"Namespace {namespace} not found"
            raise ApiException(status=404, reason=msg)
        if not watch:
            if field_selector:
                match = re.match(r"metadata\.name=(.*)$", field_selector)
                assert match and match.group(1)
                try:
                    job = self._get_object(namespace, "Job", match.group(1))
                    return V1JobList(kind="Job", items=[job])
                except ApiException:
                    return V1JobList(kind="Job", items=[])
            else:
                jobs = []
                if "Job" in self._objects[namespace]:
                    for obj in self._objects[namespace]["Job"].values():
                        if _check_labels(obj.metadata.labels, label_selector):
                            jobs.append(obj)
                return V1JobList(kind="Job", items=jobs)

        # All watches must not preload content since we're returning raw JSON.
        # This is done by the Kubernetes API Watch object.
        assert not _preload_content

        # Return the mock response expected by the Kubernetes API.
        stream = self._event_streams[namespace]["Job"]
        return stream.build_watch_response(
            resource_version,
            timeout_seconds,
            field_selector=field_selector,
            label_selector=label_selector,
        )

    async def read_namespaced_job(self, name: str, namespace: str) -> V1Job:
        """Read a job object.

        Parameters
        ----------
        name
            Name of the job.
        namespace
            Namespace of the job.

        Returns
        -------
        kubernetes_asyncio.client.V1Job
            Job object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the job was not found.
        """
        self._maybe_error("read_namespaced_job", name, namespace)
        return self._get_object(namespace, "Job", name)

    # NAMESPACE API

    async def create_namespace(self, body: V1Namespace) -> None:
        """Create a namespace.

        The mock doesn't truly track namespaces since it autocreates them when
        an object is created in that namespace (maybe that behavior should be
        optional). However, this method detects conflicts and stores the
        ``V1Namespace`` object so that it can be verified.

        Parameters
        ----------
        body
            Namespace to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the namespace already exists.
        """
        self._maybe_error("create_namespace", body)
        self._update_metadata(body, "v1", "Namespace", None)
        name = body.metadata.name
        if name in self._objects:
            msg = f"Namespace {name} already exists"
            raise ApiException(status=409, reason=msg)
        self._store_object(name, "Namespace", name, body)

    async def delete_namespace(
        self,
        name: str,
        *,
        grace_period_seconds: int | None = None,
        body: V1DeleteOptions | None = None,
    ) -> None:
        """Delete a namespace.

        This also immediately removes all objects in the namespace.

        Parameters
        ----------
        name
            Namespace to delete.
        grace_period_seconds
            Grace period for object deletion (currently ignored).
        body
            Delete options (currently ignored).

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error("delete_namespace")
        if name not in self._objects:
            raise ApiException(status=404, reason=f"{name} not found")
        del self._objects[name]

    async def read_namespace(self, name: str) -> V1Namespace:
        """Return the namespace object for a namespace.

        Parameters
        ----------
        name
            Name of namespace to retrieve.

        Returns
        -------
        kubernetes_asyncio.client.V1Namespace
            Corresponding namespace object. If `create_namespace` has
            been called, will return the stored object. Otherwise, returns a
            synthesized ``V1Namespace`` object if the namespace has been
            implicitly created.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error("read_namespace", name)
        if name not in self._objects:
            msg = f"Namespace {name} not found"
            raise ApiException(status=404, reason=msg)
        try:
            return self._get_object(name, "Namespace", name)
        except ApiException:
            return V1Namespace(metadata=V1ObjectMeta(name=name))

    async def list_namespace(self) -> V1NamespaceList:
        """List known namespaces.

        Returns
        -------
        kubernetes_asyncio.client.V1NamespaceList
            All namespaces, whether implicitly created or not. These will be
            the actual ``V1Namespace`` objects if one was stored, otherwise
            synthesized namespace objects.
        """
        self._maybe_error("list_namespace")
        namespaces = []
        for namespace in self._objects:
            namespaces.append(await self.read_namespace(namespace))
        return V1NamespaceList(items=namespaces)

    # NETWORKPOLICY API

    async def create_namespaced_network_policy(
        self, namespace: str, body: V1NetworkPolicy
    ) -> None:
        """Create a network policy object.

        Parameters
        ----------
        namespace
            Namespace in which to create the object.
        body
            Object to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error("create_namespaced_network_policy", namespace, body)
        self._update_metadata(
            body, "networking.k8s.io/v1", "NetworkPolicy", namespace
        )
        name = body.metadata.name
        self._store_object(namespace, "NetworkPolicy", name, body)

    # NODE API

    async def list_node(self) -> V1NodeList:
        """List node information.

        Returns
        -------
        kubernetes_asyncio.client.V1NodeList
            The node information previouslyl stored with `set_nodes_for_test`,
            if any.
        """
        self._maybe_error("list_node")
        return self._nodes

    # PERSISTENTVOLUMECLAIM API

    async def create_namespaced_persistent_volume_claim(
        self, namespace: str, body: V1PersistentVolumeClaim
    ) -> None:
        """Create a persistent volume claim.

        Parameters
        ----------
        namespace
            Namespace in which to create the persistent volume claim.
        body
            Persistent volume claim to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the persistent volume claim already
            exists.
        """
        self._maybe_error(
            "create_namespaced_persistent_volume_claim", namespace, body
        )
        self._update_metadata(body, "v1", "PersistentVolumeClaim", namespace)
        self._store_object(
            namespace, "PersistentVolumeClaim", body.metadata.name, body
        )

    # POD API

    async def create_namespaced_pod(self, namespace: str, body: V1Pod) -> None:
        """Create a pod object.

        If ``initial_pod_phase`` on the mock Kubernetes object is set to
        ``Running``, set the state to ``Running`` and generate a startup
        event. Otherwise, the status is set to whatever ``initial_pod_phase``
        is set to, and no event is generated.

        Parameters
        ----------
        namespace
            Namespace in which to create the pod.
        body
            Pod specification.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the pod already exists.
        """
        self._maybe_error("create_namespaced_pod", namespace, body)
        self._update_metadata(body, "v1", "Pod", namespace)
        body.status = V1PodStatus(phase=self.initial_pod_phase)
        stream = self._event_streams[namespace]["Pod"]
        body.metadata.resource_version = stream.next_resource_version
        self._store_object(namespace, "Pod", body.metadata.name, body)
        stream.add_event({"type": "ADDED", "object": body.to_dict()})
        if self.initial_pod_phase == "Running":
            event = CoreV1Event(
                metadata=V1ObjectMeta(
                    name=f"{body.metadata.name}-start", namespace=namespace
                ),
                message=f"Pod {body.metadata.name} started",
                involved_object=V1ObjectReference(
                    kind="Pod", name=body.metadata.name, namespace=namespace
                ),
            )
            await self.create_namespaced_event(namespace, event)

    async def delete_namespaced_pod(
        self,
        name: str,
        namespace: str,
        *,
        grace_period_seconds: int | None = None,
        body: V1DeleteOptions | None = None,
    ) -> V1Status:
        """Delete a pod object.

        Parameters
        ----------
        name
            Name of pod to delete.
        namespace
            Namespace of pod to delete.
        grace_period_seconds
            Grace period for object deletion (currently ignored).
        body
            Delete options (currently ignored).

        Returns
        -------
        kubernetes_asyncio.client.V1Status
            Success status.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the pod was not found.
        """
        self._maybe_error("delete_namespaced_pod", name, namespace)
        pod = self._get_object(namespace, "Pod", name)
        result = self._delete_object(namespace, "Pod", name)
        stream = self._event_streams[namespace]["Pod"]
        stream.add_event({"type": "DELETED", "object": pod.to_dict()})
        return result

    async def list_namespaced_pod(
        self,
        namespace: str,
        *,
        field_selector: Optional[str] = None,
        label_selector: Optional[str] = None,
        resource_version: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: Optional[int] = None,
    ) -> V1PodList | Mock:
        """List pod objects in a namespace.

        This does support watches.

        Parameters
        ----------
        namespace
            Namespace of pods to list.
        field_selector
            Only ``metadata.name=...`` is supported. It is parsed to find the
            pod name and only pods matching that name will be returned.
        label_selector
            Only pods with labels matching all of these will be returned.
        resource_version
            Where to start in the event stream when performing a watch. If
            `None`, starts with the next change.
        timeout_seconds
            How long to return events for before exiting when performing a
            watch.
        watch
            Whether to act as a watch.
        _preload_content
            Verified to be `False` when performing a watch.
        _request_timeout
            Ignored, accepted for compatibility with the watch API.

        Returns
        -------
        kubernetes_asyncio.client.V1PodList or unittest.mock.Mock
            List of pods in that namespace, when not called as a watch. If
            called as a watch, returns a mock ``aiohttp.Response`` with a
            ``readline`` metehod that yields the events.

        Raises
        ------
        AssertionError
            Some other ``field_selector`` was provided.
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error("list_namespaced_pod", namespace, field_selector)
        if namespace not in self._objects:
            msg = f"Namespace {namespace} not found"
            raise ApiException(status=404, reason=msg)
        if not watch:
            if field_selector:
                match = re.match(r"metadata\.name=(.*)$", field_selector)
                assert match and match.group(1)
                try:
                    pod = self._get_object(namespace, "Pod", match.group(1))
                    if _check_labels(pod.metadata.labels, label_selector):
                        return V1PodList(kind="Pod", items=[pod])
                    return V1PodList(kind="Pod", items=[])
                except ApiException:
                    return V1PodList(kind="Pod", items=[])
            else:
                pods = []
                if "Pod" in self._objects[namespace]:
                    for obj in self._objects[namespace]["Pod"].values():
                        if _check_labels(obj.metadata.labels, label_selector):
                            pods.append(obj)
                return V1PodList(kind="Pod", items=pods)

        # All watches must not preload content since we're returning raw JSON.
        # This is done by the Kubernetes API Watch object.
        assert not _preload_content

        # Return the mock response expected by the Kubernetes API.
        stream = self._event_streams[namespace]["Pod"]
        return stream.build_watch_response(
            resource_version,
            timeout_seconds,
            field_selector=field_selector,
            label_selector=label_selector,
        )

    async def patch_namespaced_pod_status(
        self, name: str, namespace: str, body: list[dict[str, Any]]
    ) -> V1Secret:
        """Patch the status of a pod object.

        Parameters
        ----------
        name
            Name of pod object.
        namespace
            Namespace of secret object.
        body
            Patches to apply. Only patches with ``op`` of ``replace`` are
            supported, and only with ``path`` of ``/status/phase``.

        Returns
        -------
        kubernetes_asyncio.client.V1Pod
            Patched pod object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the secret does not exist.
        AssertionError
            Raised if any other type of patch was provided.
        """
        self._maybe_error("patch_namespaced_pod", name, namespace)
        pod = copy.deepcopy(self._get_object(namespace, "Pod", name))
        for change in body:
            assert change["op"] == "replace"
            assert change["path"] == "/status/phase"
            pod.status.phase = change["value"]
        stream = self._event_streams[namespace]["Pod"]
        pod.metadata.resource_version = stream.next_resource_version
        self._store_object(namespace, "Pod", name, pod, replace=True)
        stream.add_event({"type": "MODIFIED", "object": pod.to_dict()})
        return pod

    async def read_namespaced_pod(self, name: str, namespace: str) -> V1Pod:
        """Read a pod object.

        Parameters
        ----------
        name
            Name of the pod.
        namespace
            Namespace of the pod.

        Returns
        -------
        kubernetes_asyncio.client.V1Pod
            Pod object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the pod was not found.
        """
        self._maybe_error("read_namespaced_pod", name, namespace)
        return self._get_object(namespace, "Pod", name)

    async def read_namespaced_pod_status(
        self, name: str, namespace: str
    ) -> V1Pod:
        """Read the status of a pod.

        Parameters
        ----------
        name
            Name of the pod.
        namespace
            Namespace of the pod.

        Returns
        -------
        kubernetes_asyncio.client.V1Pod
            Pod object. The Kubernetes API returns a ``V1Pod`` rather than, as
            expected, a ``V1PodStatus``. Presumably the acutal API populates
            only the status portion, but we return the whole pod for testing
            purposes since it shouldn't matter.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the pod was not found.
        """
        self._maybe_error("read_namespaced_pod_status", name, namespace)
        return self._get_object(namespace, "Pod", name)

    # RESOURCEQUOTA API

    async def create_namespaced_resource_quota(
        self, namespace: str, body: V1ResourceQuota
    ) -> None:
        """Create a resource quota object.

        Parameters
        ----------
        namespace
            Namespace in which to create the object.
        body
            Object to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error("create_namespaced_resource_quota", namespace, body)
        self._update_metadata(body, "v1", "ResourceQuota", namespace)
        name = body.metadata.name
        self._store_object(namespace, "ResourceQuota", name, body)

    async def read_namespaced_resource_quota(
        self, name: str, namespace: str
    ) -> V1ResourceQuota:
        """Read a resource quota object.

        Parameters
        ----------
        name
            Name of object.
        namespace
            Namespace of object.

        Returns
        -------
        kubernetes_asyncio.client.V1ResourceQuota
            Corresponding object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the resource quota was not found.
        """
        self._maybe_error("read_namespaced_resource_quota", name, namespace)
        return self._get_object(namespace, "ResourceQuota", name)

    # SECRETS API

    async def create_namespaced_secret(
        self, namespace: str, body: V1Secret
    ) -> None:
        """Create a secret object.

        Parameters
        ----------
        namespace
            Namespace in which to create the object.
        body
            Object to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error("create_namespaced_secret", namespace, body)
        self._update_metadata(body, "v1", "Secret", namespace)
        self._store_object(namespace, "Secret", body.metadata.name, body)

    async def patch_namespaced_secret(
        self, name: str, namespace: str, body: list[dict[str, Any]]
    ) -> V1Secret:
        """Patch a secret object.

        Parameters
        ----------
        name
            Name of secret object.
        namespace
            Namespace of secret object.
        body
            Patches to apply. Only patches with ``op`` of ``replace`` are
            supported, and only with ``path`` of either
            ``/metadata/annotations`` or ``/metadata/labels``.

        Returns
        -------
        kubernetes_asyncio.client.V1Secret
            Patched secret object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the secret does not exist.
        AssertionError
            Raised if any other type of patch was provided.
        """
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
        """Read a secret.

        Parameters
        ----------
        name
            Name of secret.
        namespace
            Namespace of secret.

        Returns
        -------
        kubernetes_asyncio.client.V1Secret
            Requested secret.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the secret does not exist.
        """
        self._maybe_error("read_namespaced_secret", name, namespace)
        return self._get_object(namespace, "Secret", name)

    async def replace_namespaced_secret(
        self, name: str, namespace: str, body: V1Secret
    ) -> None:
        """Replace a secret.

        Parameters
        ----------
        name
            Name of secret.
        namespace
            Namespace of secret.
        body
            New body of secret.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the secret does not exist.
        """
        self._maybe_error("replace_namespaced_secret", namespace, body)
        self._store_object(namespace, "Secret", name, body, replace=True)

    # SERVICE API

    async def create_namespaced_service(
        self, namespace: str, body: V1Service
    ) -> None:
        """Create a service object.

        Parameters
        ----------
        namespace
            Namespace in which to create the object.
        body
            Object to create.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 409 status if the object already exists.
        """
        self._maybe_error("create_namespaced_service", namespace, body)
        self._update_metadata(body, "v1", "Service", namespace)
        self._store_object(namespace, "Service", body.metadata.name, body)

    async def delete_namespaced_service(
        self,
        name: str,
        namespace: str,
        *,
        grace_period_seconds: int | None = None,
        body: V1DeleteOptions | None = None,
    ) -> V1Status:
        """Delete a service object.

        Parameters
        ----------
        name
            Name of service to delete.
        namespace
            Namespace of service to delete.
        grace_period_seconds
            Grace period for object deletion (currently ignored).
        body
            Delete options (currently ignored).

        Returns
        -------
        kubernetes_asyncio.client.V1Status
            Success status.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the service was not found.
        """
        self._maybe_error("delete_namespaced_service", name, namespace)
        return self._delete_object(namespace, "Service", name)

    async def list_namespaced_service(
        self,
        namespace: str,
        *,
        field_selector: Optional[str] = None,
        label_selector: Optional[str] = None,
        resource_version: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: Optional[int] = None,
    ) -> V1ServiceList | Mock:
        """List service objects in a namespace.

        This does support watches.

        Parameters
        ----------
        namespace
            Namespace of services to list.
        field_selector
            Only ``metadata.name=...`` is supported. It is parsed to find the
            service name and only services matching that name will be returned.
        label_selector
            Which events to retrieve when performing a watch.  All
            labels must match.
        resource_version
            Where to start in the event stream when performing a watch. If
            `None`, starts with the next change.
        timeout_seconds
            How long to return events for before exiting when performing a
            watch.
        watch
            Whether to act as a watch.
        _preload_content
            Verified to be `False` when performing a watch.
        _request_timeout
            Ignored, accepted for compatibility with the watch API.

        Returns
        -------
        kubernetes_asyncio.client.V1ServiceList or unittest.mock.Mock
            List of services in that namespace, when not called as a watch. If
            called as a watch, returns a mock ``aiohttp.Response`` with a
            ``readline`` metehod that yields the events.

        Raises
        ------
        AssertionError
            Some other ``field_selector`` was provided.
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error("list_namespaced_service", namespace, field_selector)
        if namespace not in self._objects:
            msg = f"Namespace {namespace} not found"
            raise ApiException(status=404, reason=msg)
        if not watch:
            if field_selector:
                match = re.match(r"metadata\.name=(.*)$", field_selector)
                assert match and match.group(1)
                try:
                    service = self._get_object(
                        namespace, "Service", match.group(1)
                    )
                    return V1ServiceList(kind="Service", items=[service])
                except ApiException:
                    return V1ServiceList(kind="Service", items=[])
            else:
                services = []
                if "Service" in self._objects[namespace]:
                    for obj in self._objects[namespace]["Service"].values():
                        if _check_labels(obj.metadata.labels, label_selector):
                            services.append(obj)
                return V1ServiceList(kind="Service", items=services)

        # All watches must not preload content since we're returning raw JSON.
        # This is done by the Kubernetes API Watch object.
        assert not _preload_content

        # Return the mock response expected by the Kubernetes API.
        stream = self._event_streams[namespace]["Service"]
        return stream.build_watch_response(
            resource_version,
            timeout_seconds,
            field_selector=field_selector,
            label_selector=label_selector,
        )

    async def read_namespaced_service(
        self, name: str, namespace: str
    ) -> V1Service:
        """Read a service.

        Parameters
        ----------
        name
            Name of service.
        namespace
            Namespace of service.

        Returns
        -------
        kubernetes_asyncio.client.V1Service
            Requested service.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the service does not exist.
        """
        self._maybe_error("read_namespaced_service", name, namespace)
        return self._get_object(namespace, "Service", name)

    # Internal helper functions.

    def _delete_object(self, namespace: str, key: str, name: str) -> V1Status:
        """Delete an object from internal data structures.

        Returns
        -------
        kubernetes_asyncio.client.V1Status
            200 return status if the object was found and deleted.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with a 404 status if the object is not found.
        """
        # Called for the side effect of raising an exception if the object is
        # not found.
        self._get_object(namespace, key, name)

        del self._objects[namespace][key][name]
        return V1Status(code=200)

    def _get_object(self, namespace: str, key: str, name: str) -> Any:
        """Retrieve an object from internal data structures.

        Returns
        -------
        Any
            Object if found.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with a 404 status if the object is not found.
        """
        if namespace not in self._objects:
            reason = f"{namespace}/{name} not found"
            raise ApiException(status=404, reason=reason)
        if name not in self._objects[namespace].get(key, {}):
            reason = f"{namespace}/{name} not found"
            raise ApiException(status=404, reason=reason)
        return self._objects[namespace][key][name]

    def _maybe_error(self, method: str, *args: Any) -> None:
        """Helper function to avoid using class method call syntax."""
        if self.error_callback:
            callback = self.error_callback
            callback(method, *args)

    def _store_object(
        self,
        namespace: str,
        key: str,
        name: str,
        obj: Any,
        replace: bool = False,
    ) -> None:
        """Store an object in internal data structures.

        Parameters
        ----------
        namespace
            Namespace in which to store the object.
        key
            Key under which to store the object (generally the kind).
        name
            Name of object.
        obj
            Object to store.
        replace
            If `True`, the object must already exist, to mirror the Kubernetes
            replace semantices. If `False`, a conflict error is raised if the
            object already exists.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the object does not exist and ``replace``
            was `True`, and with 409 status if the object does exist and
            ``replace`` was `False`.
        """
        if replace:
            self._get_object(namespace, key, name)
        else:
            if namespace not in self._objects:
                self._objects[namespace] = {}
            if key not in self._objects[namespace]:
                self._objects[namespace][key] = {}
            if name in self._objects[namespace][key]:
                msg = f"{namespace}/{name} exists"
                raise ApiException(status=409, reason=msg)
        self._objects[namespace][key][name] = obj

    def _update_metadata(
        self, body: Any, api_version: str, kind: str, namespace: str | None
    ) -> None:
        """Check and potentially update the metadata of a stored object.

        The Kubernetes API allows the ``api_version``, ``kind``, and
        ``metadata.namespace`` attributes to be omitted since they can be
        determined from the method called or its parameters. Implement the
        same logic, but if they are provided in the object, require that they
        be correct (match the parameters inferred from the call).

        Parameters
        ----------
        body
            Object being stored. Updated in place with namespace, kind, and
            API version information.
        api_version
            Expected API version of object.
        kind
            Expected kind of object.
        namespace
            Namespace in which it is being stored, or `None` for objects that
            are not namespaced.

        Raises
        ------
        AssertionError
            Raised if the namespace, kind, or API version was provided but
            didn't match the expected value.
        """
        if body.api_version:
            assert body.api_version == api_version
        else:
            body.api_version = api_version
        if body.kind:
            assert body.kind == kind
        else:
            body.kind = kind
        if body.metadata.namespace:
            assert body.metadata.namespace == namespace
        else:
            body.metadata.namespace = namespace


def patch_kubernetes() -> Iterator[MockKubernetesApi]:
    """Replace the Kubernetes API with a mock class.

    Returns
    -------
    MockKubernetesApi
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
        for api in (
            "BatchV1Api",
            "CoreV1Api",
            "CustomObjectsApi",
            "NetworkingV1Api",
        ):
            patcher = patch.object(client, api)
            mock_class = patcher.start()
            mock_class.return_value = mock_api
            patchers.append(patcher)
        mock_api_client = Mock(spec=client.ApiClient)
        mock_api_client.close = AsyncMock()
        with patch.object(client, "ApiClient") as mock_client:
            mock_client.return_value = mock_api_client
            os.environ["KUBERNETES_PORT"] = "tcp://10.0.0.1:443"
            yield mock_api
            del os.environ["KUBERNETES_PORT"]
        for patcher in patchers:
            patcher.stop()
