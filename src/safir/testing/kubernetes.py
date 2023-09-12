"""Mock Kubernetes API for testing."""

from __future__ import annotations

import copy
import json
import os
import re
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import timedelta
from typing import Any
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
from typing_extensions import Protocol

from ..asyncio import AsyncMultiQueue

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
    dict of str
        Dictionary of required labels to their required values.

    Raises
    ------
    AssertionError
        Raised if the label selector string is not a supported syntax.
    """
    result = {}
    for requirement in label_selector.split(","):
        match = re.match(r"([^!=]+)==?(.*)", requirement)
        assert match
        assert match.group(1)
        assert match.group(2)
        result[match.group(1)] = match.group(2)
    return result


def _check_labels(
    obj_labels: dict[str, str] | None, label_selector: str | None
) -> bool:
    """Check whether an object's labels match a label selector.

    Parameters
    ----------
    obj_labels
        Kubernetes object labels.
    label_selector
        Label selector in string form.

    Returns
    -------
    bool
        Whether this object matches the label selector.
    """
    # Everything matches the absence of a selector.
    if not label_selector:
        return True

    # If there are no labels but a non-empty selector, it doesn't match.
    if not obj_labels:
        return False

    # Check that all labels match the labels of the object.
    labels = _parse_label_selector(label_selector)
    for label in labels:
        if label not in obj_labels or labels[label] != obj_labels[label]:
            return False
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
        new_value = value
        if isinstance(value, dict):
            new_value = strip_none(value)
        elif isinstance(value, list):
            list_result = []
            for item in value:
                if isinstance(item, dict):
                    list_result.append(strip_none(item))
                else:
                    list_result.append(item)
            new_value = list_result
        result[key] = new_value
    return result


class _KubernetesModel(Protocol):
    """Protocol describing common features of Kubernetes objects.

    The kubernetes_asyncio_ library doesn't provide full typing of its methods
    or objects, so use a protocol to describe the functionality that we rely
    on when passing a generic object around.
    """

    def to_dict(
        self, serialize: bool = False  # noqa: FBT001, FBT002
    ) -> dict[str, Any]:
        ...


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
        self._queue = AsyncMultiQueue[dict[str, Any]]()

    @property
    def next_resource_version(self) -> str:
        """Resource version of the next event.

        This starts with ``1`` to ensure that a resource version of ``0`` is
        special and means to return all known events, so it must be adjusted
        when indexing into a list of events.
        """
        return str(self._queue.qsize() + 1)

    def add_custom_event(self, action: str, obj: dict[str, Any]) -> None:
        """Add a new event for a custom object and notify all watchers.

        Parameters
        ----------
        action
            Action of the event.
        obj
            Custom object triggering the event.
        """
        self._queue.put({"type": action, "object": obj})

    def add_event(self, action: str, obj: _KubernetesModel) -> None:
        """Add a new event and notify all watchers.

        Parameters
        ----------
        action
            Action of the event.
        obj
            Object triggering the event.
        """
        event = {"type": action, "object": obj.to_dict(serialize=True)}
        self._queue.put(event)

    def build_watch_response(
        self,
        resource_version: str | None = None,
        timeout_seconds: int | None = None,
        *,
        field_selector: str | None = None,
        label_selector: str | None = None,
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
            Limit the returned events to the objects matching the selector.
            If set, it must be set to ``metadata.name=...`` to match a
            specific object name.
        label_selector
            Limit the returned events to the objects matching this label
            selector.

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
            Limit the returned events to the objects matching the selector.
            If set, it must be set to ``metadata.name=...`` to match a
            specific object name.
        label_selector
            Limit the returned events to the objects matching this label
            selector.

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
            timeout = timedelta(seconds=timeout_seconds)

        # Parse the field selector, if one was provided.
        name = None
        if field_selector:
            match = re.match(r"metadata\.name=(.*)$", field_selector)
            assert match
            assert match.group(1)
            name = match.group(1)

        # Construct the iterator.
        async def next_event() -> AsyncIterator[bytes]:
            if resource_version:
                start = int(resource_version)
            else:
                start = self._queue.qsize()
            try:
                async for event in self._queue.aiter_from(start, timeout):
                    if name and event["object"]["metadata"]["name"] != name:
                        continue
                    labels = event["object"]["metadata"]["labels"]
                    if not _check_labels(labels, label_selector):
                        continue
                    yield json.dumps(event).encode()
            except TimeoutError:
                yield b""

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
    ``V1Namespace`` object or emit events for `list_namespace` watches. To
    verify that a namespace was properly created (although not the order of
    creation), check for the namespace object explicitly with `read_namespace`
    or `list_namespace`.

    Objects stored with ``create_*`` or ``replace_*`` methods are **NOT**
    copied. The object provided will be stored, so changing that object will
    change the object returned by subsequent API calls. Likewise, the object
    returned by ``read_*`` calls will be the same object stored in the mock,
    and changing it will change the mock's data. (Sometimes this is the
    desired behavior, sometimes it isn't; we had to pick one and this is the
    approach we picked.)

    Not all methods are implemented for each kind, and not all ``list_*`` APIs
    support watches. In general, APIs are only implemented when some other
    package needs them.

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
        self.error_callback: Callable[..., None] | None = None
        self.initial_pod_phase = "Running"

        self._custom_kinds: dict[str, str] = {}
        self._nodes = V1NodeList(items=[])
        self._objects: dict[str, dict[str, dict[str, Any]]] = {}
        self._events: defaultdict[str, list[CoreV1Event]] = defaultdict(list)
        self._namespace_stream = _EventStream()
        self._event_streams: defaultdict[str, defaultdict[str, _EventStream]]
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
            for _name, obj in sorted(self._objects[namespace][key].items()):
                results.append(obj)
        return results

    def get_namespace_objects_for_test(self, namespace: str) -> list[Any]:
        """Return all objects in the given namespace.

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
        if body["metadata"].get("namespace"):
            assert namespace == body["metadata"]["namespace"]
        else:
            body["metadata"]["namespace"] = namespace
        stream = self._event_streams[namespace][key]
        body["metadata"]["resourceVersion"] = stream.next_resource_version
        self._store_object(namespace, key, body["metadata"]["name"], body)
        stream.add_custom_event("ADDED", body)

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
        obj = self._get_object(namespace, key, name)
        stream = self._event_streams[namespace][key]
        stream.add_custom_event("DELETED", obj)
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
        results: list[dict[str, Any]] = []
        for namespace in self._objects:
            results.extend(self._objects[namespace].get(key, {}).values())
        return {"items": results}

    async def list_namespaced_custom_object(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        *,
        field_selector: str | None = None,
        label_selector: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int | None = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: int | None = None,
    ) -> V1IngressList | Mock:
        """List custom objects in a namespace.

        This does support watches.

        Parameters
        ----------
        group
            API group for this custom object.
        version
            API version for this custom object.
        namespace
            Namespace of ingresss to list.
        plural
            API plural for this custom object.
        field_selector
            Only ``metadata.name=...`` is supported. It is parsed to find the
            ingress name and only ingresss matching that name will be returned.
        label_selector
            Which objects to retrieve. All labels must match.
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
        dict or unittest.mock.Mock
            List of custom objects in that namespace as a dict with one key,
           ``items``, when not called as a watch. If called as a watch,
           returns a mock ``aiohttp.Response`` with a ``readline`` metehod
           that yields the events.

        Raises
        ------
        AssertionError
            Some other ``field_selector`` was provided.
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error(
            "list_namespaced_custom_object",
            group,
            version,
            namespace,
            plural,
            field_selector,
        )
        key = f"{group}/{version}/{plural}"
        if namespace not in self._objects:
            msg = f"Namespace {namespace} not found"
            raise ApiException(status=404, reason=msg)
        if not watch:
            objs = self._list_objects(
                namespace, key, field_selector, label_selector
            )
            return {"items": objs}

        # All watches must not preload content since we're returning raw JSON.
        # This is done by the Kubernetes API Watch object.
        assert not _preload_content

        # Return the mock response expected by the Kubernetes API.
        stream = self._event_streams[namespace][key]
        return stream.build_watch_response(
            resource_version,
            timeout_seconds,
            field_selector=field_selector,
            label_selector=label_selector,
        )

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
        stream = self._event_streams[namespace][key]
        obj["metadata"]["resourceVersion"] = stream.next_resource_version
        self._store_object(namespace, key, name, obj, replace=True)
        stream.add_custom_event("MODIFIED", obj)
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
        stream = self._event_streams[namespace][key]
        body["metadata"]["resourceVersion"] = stream.next_resource_version
        self._store_object(namespace, key, name, body, replace=True)
        stream.add_custom_event("MODIFIED", body)

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
        stream.add_event("ADDED", body)
        self._events[namespace].append(body)

    async def list_namespaced_event(
        self,
        namespace: str,
        *,
        field_selector: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int | None = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: int | None = None,
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
        stream = self._event_streams[namespace]["Ingress"]
        body.metadata.resource_version = stream.next_resource_version
        body.status = V1IngressStatus(
            load_balancer=V1LoadBalancerStatus(ingress=[])
        )
        self._store_object(namespace, "Ingress", name, body)
        stream.add_event("ADDED", body)

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
        stream.add_event("DELETED", ingress)
        return self._delete_object(namespace, "Ingress", name)

    async def list_namespaced_ingress(
        self,
        namespace: str,
        *,
        field_selector: str | None = None,
        label_selector: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int | None = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: int | None = None,
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
            Which objects to retrieve. All labels must match.
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
            ingresses = self._list_objects(
                namespace, "Ingress", field_selector, label_selector
            )
            return V1IngressList(kind="Ingress", items=ingresses)

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
        stream.add_event("MODIFIED", ingress)
        return ingress

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

    # JOB API

    async def create_namespaced_job(self, namespace: str, body: V1Job) -> None:
        """Create a job object.

        A pod corresponding to this job will also be created. The pod will
        have a label ``job-name`` set to the name of the ``Job`` object, and
        will honor the ``name`` or ``generateName`` metadata from the pod spec
        in the ``Job``. If neither is set, it will use the job name followed
        by ``-`` as the base for a generated name.

        If ``initial_pod_phase`` on the mock is set to ``Running``, the
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
        stream = self._event_streams[namespace]["Job"]
        body.metadata.resource_version = stream.next_resource_version
        self._store_object(namespace, "Job", name, body)

        # Normally, Kubernetes will immediately spawn a Pod using the
        # specification in the Job. Simulate that here.
        pod = V1Pod(
            metadata=body.spec.template.metadata or V1ObjectMeta(),
            spec=body.spec.template.spec,
        )
        if not pod.metadata.name:
            if not pod.metadata.generate_name:
                pod.metadata.generate_name = f"{name}-"
            base = pod.metadata.generate_name
            pod.metadata.name = base + os.urandom(3).hex()[:5]
        pod.metadata.labels["job-name"] = name
        pod.metadata.namespace = namespace
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
        stream.add_event("DELETED", job)
        return self._delete_object(namespace, "Job", name)

    async def list_namespaced_job(
        self,
        namespace: str,
        *,
        field_selector: str | None = None,
        label_selector: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int | None = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: int | None = None,
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
            Which objects to retrieve. All labels must match.
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
            jobs = self._list_objects(
                namespace, "Job", field_selector, label_selector
            )
            return V1PodList(kind="Job", items=jobs)

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
        self._namespace_stream.add_event("ADDED", body)

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
        try:
            body = await self.read_namespace(name)
            self._namespace_stream.add_event("DELETED", body)
        except ApiException:
            pass
        del self._objects[name]

    async def read_namespace(self, name: str) -> V1Namespace:
        """Return the namespace object for a namespace.

        This will only return a namespace object if one was created via
        `create_namespace`, not if one was implicitly added by creating some
        other object.

        Parameters
        ----------
        name
            Name of namespace to retrieve.

        Returns
        -------
        kubernetes_asyncio.client.V1Namespace
            Corresponding namespace object. If `create_namespace` has not been
            called, but the namespace was added implicitly, an exception will
            be raised.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error("read_namespace", name)
        return self._get_object(name, "Namespace", name)

    async def list_namespace(
        self,
        *,
        field_selector: str | None = None,
        label_selector: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int | None = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: int | None = None,
    ) -> V1NamespaceList | Mock:
        """List namespaces.

        This does support watches. Only namespaces that are explicitly
        created with `create_namespace` will be shown, not ones that were
        implicitly created by creating some other object.

        Parameters
        ----------
        namespace
            Namespace of jobs to list.
        field_selector
            Only ``metadata.name=...`` is supported. It is parsed to find the
            namespace name and only the namespace matching that name will be
            returned.
        label_selector
            Which objects to retrieve. All labels must match.
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
            List of namespaces, when not called as a watch. If called as a
            watch, returns a mock ``aiohttp.Response`` with a ``readline``
            metehod that yields the events.

        Raises
        ------
        AssertionError
            Some other ``field_selector`` was provided.
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the namespace does not exist.
        """
        self._maybe_error("list_namespace")

        # We annoyingly have to duplicate a bunch of logic from _list_objects
        # because namespaces aren't stored under a single namespace.
        if not watch:
            if field_selector:
                match = re.match(r"metadata\.name=(.*)$", field_selector)
                if not match or not match.group(1):
                    msg = f"Field selector {field_selector} not supported"
                    raise ValueError(msg)
                try:
                    name = match.group(1)
                    obj = self._get_object(name, "Namespace", name)
                    if _check_labels(obj.metadata.labels, label_selector):
                        return [obj]
                    else:
                        return []
                except ApiException:
                    return []
            namespaces = []
            for name in self._objects:
                try:
                    namespace = await self.read_namespace(name)
                except ApiException:
                    continue
                if _check_labels(namespace.metadata.labels, label_selector):
                    namespaces.append(namespace)
            return V1NamespaceList(items=namespaces)

        # All watches must not preload content since we're returning raw JSON.
        # This is done by the Kubernetes API Watch object.
        assert not _preload_content

        # Return the mock response expected by the Kubernetes API.
        return self._namespace_stream.build_watch_response(
            resource_version,
            timeout_seconds,
            field_selector=field_selector,
            label_selector=label_selector,
        )

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

    async def read_namespaced_network_policy(
        self, name: str, namespace: str
    ) -> V1Pod:
        """Read a network policy object.

        Parameters
        ----------
        name
            Name of the network policy.
        namespace
            Namespace of the network policy.

        Returns
        -------
        kubernetes_asyncio.client.V1NetworkPolicy
            Network policy object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the network policy was not found.
        """
        self._maybe_error("read_namespaced_network_policy", name, namespace)
        return self._get_object(namespace, "NetworkPolicy", name)

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

    async def read_namespaced_persistent_volume_claim(
        self, name: str, namespace: str
    ) -> V1PersistentVolumeClaim:
        """Read a persistent volume claim.

        Parameters
        ----------
        name
            Name of the persistent volume claim.
        namespace
            Namespace of the persistent volume claim.

        Returns
        -------
        kubernetes_asyncio.client.V1PersistentVolumeClaim
            Persistent volume claim object.

        Raises
        ------
        kubernetes_asyncio.client.ApiException
            Raised with 404 status if the persistent volume claim was not
            found.
        """
        self._maybe_error(
            "read_namespaced_persistent_volume_claim", name, namespace
        )
        return self._get_object(namespace, "PersistentVolumeClaim", name)

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
        stream.add_event("ADDED", body)
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
        stream = self._event_streams[namespace]["Pod"]
        stream.add_event("DELETED", pod)
        return self._delete_object(namespace, "Pod", name)

    async def list_namespaced_pod(
        self,
        namespace: str,
        *,
        field_selector: str | None = None,
        label_selector: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int | None = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: int | None = None,
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
            Which objects to retrieve. All labels must match.
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
            pods = self._list_objects(
                namespace, "Pod", field_selector, label_selector
            )
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
        stream.add_event("MODIFIED", pod)
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
        secret = copy.deepcopy(self._get_object(namespace, "Secret", name))
        for change in body:
            assert change["op"] == "replace"
            if change["path"] == "/metadata/annotations":
                secret.metadata.annotations = change["value"]
            elif change["path"] == "/metadata/labels":
                secret.metadata.labels = change["value"]
            else:
                raise AssertionError(f"unsupported path {change['path']}")
        self._store_object(namespace, "Secret", name, secret, replace=True)

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
        stream = self._event_streams[namespace]["Service"]
        body.metadata.resource_version = stream.next_resource_version
        self._store_object(namespace, "Service", body.metadata.name, body)
        stream.add_event("ADDED", body)

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
        service = self._get_object(namespace, "Service", name)
        stream = self._event_streams[namespace]["Service"]
        stream.add_event("DELETED", service)
        return self._delete_object(namespace, "Service", name)

    async def list_namespaced_service(
        self,
        namespace: str,
        *,
        field_selector: str | None = None,
        label_selector: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int | None = None,
        watch: bool = False,
        _preload_content: bool = True,
        _request_timeout: int | None = None,
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
            Which objects to retrieve. All labels must match.
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
            services = self._list_objects(
                namespace, "Service", field_selector, label_selector
            )
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

        Parameters
        ----------
        namespace
            Namespace from which to delete an object.
        key
            Key under which the object is stored (usually the kind).
        name
            Name of the object.

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

        Parameters
        ----------
        namespace
            Namespace from which to delete an object.
        key
            Key under which the object is stored (usually the kind).
        name
            Name of the object.

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

    def _list_objects(
        self,
        namespace: str,
        key: str,
        field_selector: str | None,
        label_selector: str | None,
    ) -> list[Any]:
        """List objects, possibly with selector restrictions.

        Parameters
        ----------
        namespace
            Namespace in which to list objects.
        key
            Key under which the object is stored (usually the kind).
        field_selector
            If present, only ``metadata.name=...`` is supported. It is parsed
            to find the object name and only an object matching that name will
            be returned.
        label_selector
            Which matching objects to retrieve by label. All labels must
            match.

        Returns
        -------
        list
            List of matching objects.
        """
        if key not in self._objects[namespace]:
            return []

        # If there is a field selector, only name selectors are supported and
        # we should retrieve the object by name.
        if field_selector:
            match = re.match(r"metadata\.name=(.*)$", field_selector)
            if not match or not match.group(1):
                msg = f"Field selector {field_selector} not supported"
                raise ValueError(msg)
            try:
                obj = self._get_object(namespace, key, match.group(1))
                if _check_labels(obj.metadata.labels, label_selector):
                    return [obj]
                else:
                    return []
            except ApiException:
                return []

        # Otherwise, construct the list of all objects matching the label
        # selector.
        return [
            o
            for o in self._objects[namespace][key].values()
            if _check_labels(o.metadata.labels, label_selector)
        ]

    def _maybe_error(self, method: str, *args: Any) -> None:
        """Call the error callback if one is registered.

        This is a separate helper function to avoid using class method call
        syntax.
        """
        if self.error_callback:
            callback = self.error_callback
            callback(method, *args)

    def _store_object(
        self,
        namespace: str,
        key: str,
        name: str,
        obj: Any,
        *,
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
        with patch.object(client.ApiClient, "request"):
            os.environ["KUBERNETES_PORT"] = "tcp://10.0.0.1:443"
            yield mock_api
            del os.environ["KUBERNETES_PORT"]
        for patcher in patchers:
            patcher.stop()
