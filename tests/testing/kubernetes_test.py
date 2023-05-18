"""Tests for the Kubernetes support infrastructure.

These are just basic sanity checks that the mocking is working correctly and
the basic calls work. There is no attempt to test all of the supported APIs.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest
from kubernetes_asyncio.client import (
    CoreV1Event,
    V1Container,
    V1DeleteOptions,
    V1ObjectMeta,
    V1ObjectReference,
    V1Pod,
    V1PodSpec,
    V1Secret,
)
from kubernetes_asyncio.watch import Watch

from safir.testing.kubernetes import MockKubernetesApi, strip_none


def test_strip_none() -> None:
    pod = V1Pod(
        metadata=V1ObjectMeta(name="foo"),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name="something",
                    command=["/bin/sleep", "5"],
                    image="docker.example.com/some/image:latest",
                )
            ]
        ),
    )
    assert strip_none(pod.to_dict()) == {
        "metadata": {"name": "foo"},
        "spec": {
            "containers": [
                {
                    "name": "something",
                    "command": ["/bin/sleep", "5"],
                    "image": "docker.example.com/some/image:latest",
                }
            ]
        },
    }


@pytest.mark.asyncio
async def test_mock(mock_kubernetes: MockKubernetesApi) -> None:
    custom: dict[str, Any] = {
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
    ) == {"items": [custom]}
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


async def watch_events(
    mock_kubernetes: MockKubernetesApi,
    namespace: str,
    *,
    resource_version: Optional[str] = None,
) -> list[CoreV1Event]:
    """Watch events, returning when an event with message ``Done`` is seen."""
    method = mock_kubernetes.list_namespaced_event
    watch_args = {
        "namespace": namespace,
        "timeout_seconds": 10,  # Just in case, so tests don't hang
    }
    if resource_version:
        watch_args["resource_version"] = resource_version
    async with Watch().stream(method, **watch_args) as stream:
        seen = []
        async for event in stream:
            assert event["type"] == "ADDED"
            obj = event["raw_object"]
            seen.append(obj)
            if "Done" in obj.get("message"):
                return seen
        return seen


@pytest.mark.asyncio
async def test_mock_events(mock_kubernetes: MockKubernetesApi) -> None:
    watchers = [
        asyncio.create_task(watch_events(mock_kubernetes, "stuff")),
        asyncio.create_task(watch_events(mock_kubernetes, "stuff")),
        asyncio.create_task(watch_events(mock_kubernetes, "stuff")),
    ]
    await asyncio.sleep(0.2)

    # Creating a pod should by default create an event in that namespace.
    pod = V1Pod(
        metadata=V1ObjectMeta(name="foo"),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name="something",
                    command=["/bin/sleep", "5"],
                    image="docker.example.com/some/image:latest",
                )
            ]
        ),
    )
    await mock_kubernetes.create_namespaced_pod("stuff", pod)
    some_event = CoreV1Event(
        metadata=V1ObjectMeta(name="some-event"),
        message="Some event",
        involved_object=V1ObjectReference(
            kind="Pod", name="foo", namespace="stuff"
        ),
    )
    await mock_kubernetes.create_namespaced_event("stuff", some_event)
    done_event = CoreV1Event(
        metadata=V1ObjectMeta(name="some-event"),
        message="Done",
        involved_object=V1ObjectReference(
            kind="Pod", name="foo", namespace="stuff"
        ),
    )
    await mock_kubernetes.create_namespaced_event("stuff", done_event)

    # All three watches should see the same thing.
    results = await asyncio.gather(*watchers)
    assert len(results) == 3
    assert results[0] == results[1]
    assert results[0] == results[2]
    result = results[0]
    assert result[1] == some_event.to_dict()
    assert result[2] == done_event.to_dict()

    # The first event should have been the pod running event.
    assert result[0]["message"] == "Pod foo started"
    assert result[0]["involved_object"]["kind"] == "Pod"
    assert result[0]["involved_object"]["name"] == "foo"
    assert result[0]["involved_object"]["namespace"] == "stuff"

    # Starting with resource version "1" should skip the first event, since
    # the semantics of a watch are to show any events *after* the provided
    # resource version.
    events = await watch_events(mock_kubernetes, "stuff", resource_version="1")
    assert events == result[1:]

    # Not specifying a resource version should wait for new events but not see
    # any of the existing events. (Tasks do not start immediately, so we have
    # to wait after creating the task to ensure that it starts running and
    # decides what resource version to start waiting at before we post another
    # event.)
    watcher = asyncio.create_task(watch_events(mock_kubernetes, "stuff"))
    await asyncio.sleep(0.1)
    event = CoreV1Event(
        metadata=V1ObjectMeta(name="some-event"),
        message="Done second time",
        involved_object=V1ObjectReference(
            kind="Pod", name="foo", namespace="stuff"
        ),
    )
    await mock_kubernetes.create_namespaced_event("stuff", event)
    events = await watcher
    assert len(events) == 1
    assert events[0]["message"] == "Done second time"


async def watch_pod_events(
    mock_kubernetes: MockKubernetesApi, name: str, namespace: str
) -> list[dict[str, Any]]:
    """Watch pod events, returning when the pod is deleted."""
    method = mock_kubernetes.list_namespaced_pod
    watch_args = {
        "field_selector": f"metadata.name={name}",
        "namespace": namespace,
        "timeout_seconds": 10,  # Just in case, so tests don't hang
    }
    async with Watch().stream(method, **watch_args) as stream:
        seen = []
        async for event in stream:
            seen.append(event)
            if event["type"] == "DELETED":
                return seen
        return seen


@pytest.mark.asyncio
async def test_pod_status(mock_kubernetes: MockKubernetesApi) -> None:
    pod = V1Pod(
        metadata=V1ObjectMeta(name="foo"),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name="something",
                    command=["/bin/sleep", "5"],
                    image="docker.example.com/some/image:latest",
                )
            ]
        ),
    )
    await mock_kubernetes.create_namespaced_pod("stuff", pod)
    status = await mock_kubernetes.read_namespaced_pod_status("foo", "stuff")
    assert status.status.phase == "Running"
    events = await mock_kubernetes.list_namespaced_event("stuff")
    assert len(events.items) == 1

    mock_kubernetes.initial_pod_phase = "Starting"
    pod = V1Pod(
        metadata=V1ObjectMeta(name="foo"),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name="something",
                    command=["/bin/sleep", "5"],
                    image="docker.example.com/some/image:latest",
                )
            ]
        ),
    )
    await mock_kubernetes.create_namespaced_pod("other", pod)
    status = await mock_kubernetes.read_namespaced_pod_status("foo", "other")
    assert status.status.phase == "Starting"
    events = await mock_kubernetes.list_namespaced_event("other")
    assert events.items == []
    watchers = [
        asyncio.create_task(watch_pod_events(mock_kubernetes, "foo", "other")),
        asyncio.create_task(watch_pod_events(mock_kubernetes, "foo", "other")),
        asyncio.create_task(watch_pod_events(mock_kubernetes, "foo", "other")),
    ]
    await asyncio.sleep(0.1)
    await mock_kubernetes.patch_namespaced_pod_status(
        "foo",
        "other",
        [{"op": "replace", "path": "/status/phase", "value": "Running"}],
    )
    await mock_kubernetes.delete_namespaced_pod(
        "foo",
        "other",
        grace_period_seconds=1,
        body=V1DeleteOptions(grace_period_seconds=1),
    )

    # All three watches should see the same thing.
    results = await asyncio.gather(*watchers)
    assert len(results) == 3
    assert results[0] == results[1]
    assert results[0] == results[2]
    result = results[0]
    assert result[0]["type"] == "MODIFIED"
    assert result[0]["object"]["status"]["phase"] == "Running"
    assert result[1]["type"] == "DELETED"
    assert result[1]["object"] == result[0]["object"]
