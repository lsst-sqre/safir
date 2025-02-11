########################
Using the Kubernetes API
########################

Safir-based applications are encouraged to use the `kubernetes-asyncio <https://github.com/tomplus/kubernetes_asyncio>`__ Python module.
It provides an async API for Kubernetes that will work naturally with FastAPI applications.

Most Kubernetes work can be done by calling that API directly, with no need for Safir wrapper functions.
Safir provides a convenient `~safir.kubernetes.initialize_kubernetes` function that chooses the correct way to load the Kubernetes configuration depending on whether the code is running from within or outside of a cluster, and a framework for mocking the Kubernetes API for tests.

Kubernetes support in Safir is optional.
To use it, depend on ``safir[kuberentes]``.

Initializing Kubernetes
=======================

A Kubernetes configuration must be loaded before making the first API call.
Safir provides the `~safir.kubernetes.initialize_kubernetes` async function to do this.
It doesn't take any arguments.
The Kubernetes configuration will be loaded from the in-cluster configuration path if the environment variable ``KUBERNETES_PORT`` is set, which will be set inside a cluster, and otherwise attempts to load configuration from the user's home directory.

A FastAPI application that uses Kubernetes from inside route handlers should normally call this function during application startup.
For example:

.. code-block:: python

   from collections.abc import AsyncGenerator
   from contextlib import asynccontextmanager

   from fastapi import FastAPI
   from safir.kubernetes import initialize_kubernetes


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
       await initialize_kubernetes()
       yield

Testing with mock Kubernetes
============================

The `safir.testing.kubernetes` module provides a mock Kubernetes API with a limited implementation the API, and some utility functions to use it.

Applications that want to run tests with the mock Kubernetes API should define a fixture (in ``conftest.py``) as follows:

.. code-block:: python

   from collections.abc import Iterator

   import pytest
   from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes


   @pytest.fixture
   def mock_kubernetes() -> Iterator[MockKubernetesApi]:
       yield from patch_kubernetes()

Then, when initializing Kubernetes, be sure not to import ``ApiClient``, ``CoreV1Api``, ``CustomObjectsApi``, or ``NetworkingV1Api`` directly into a module.
Instead, use:

.. code-block:: python

   from kubernetes_asyncio import client

and then use ``client.ApiClient``, ``client.CoreV1Api``, ``client.CustomObjectsApi``, or ``client.NetworkingV1Api``.
This will ensure that the Kubernetes API is mocked properly.

You can then use ``mock_kubernetes`` as a fixture.
The resulting object supports a limited subset of the ``client.CoreV1Api``, ``client.CustomObjectsApi``, and ``client.NetworkingV1Api`` method calls for creating, retrieving, modifying, and deleting objects.
The objects created by either the test or by the application code under test will be stored in memory inside the ``mock_kubernetes`` object.

All objects will be modified to add the ``api_version`` and ``kind`` fields and, if appropriate, the ``metadata.namespace`` field before being stored, so those fields are optional, as with the normal Kubernetes API.
If any of those fields are supplied, they must match the expected values for the API into which the object is passed.
If they are not, the mock will raise `AssertionError`.

Use the `~safir.testing.kubernetes.MockKubernetesApi.get_all_objects_for_test` method to retrieve all objects of a given kind, allowing comparisons against an expected list of objects.
Use the `~safir.testing.kubernetes.MockKubernetesApi.get_namespace_objects_for_test` method to retrieve all objects (of whatever kind) in a given namespace.

Limitations of the mock
-----------------------

Only a limited subset of the API is supported, and only the most commonly-used parameters of those APIs are supported.
Expect to need to add additional APIs and parameters, when testing a new application.
Contributions of those additional APIs and parameters will be gratefully reviewed and normally merged.

Namespaces are only partially modeled.
A namespace can be explicitly created with `~safir.testing.kubernetes.MockKubernetesApi.create_namespace`, in which case the provided ``V1Namespace`` object will be stored and returned by a subsequent `~safir.testing.kubernetes.MockKubernetesApi.read_namespace` or similar call.
However, namespace creation is optional.
If an object is created in a namespace, that namespace will magically come into existence, and a subsequent `~safir.testing.kubernetes.MockKubernetesApi.list_namespace` or `~safir.testing.kubernetes.MockKubernetesApi.read_namespace` call will return a synthetic namespace object.

When creating Kubernetes watches, the caller will have to pass the expected model type explicitly as the first argument to the constructor of the ``Watch`` object in order to ensure correct deserialization of the raw object when using the mock.
Unfortunately, the type autodetection support in kubernetes_asyncio_ does not work with our mock since it relies on docstring inspection.

.. warning::

   Objects stored with ``create_*`` or ``replace_*`` methods are stored directly in memory, not copied, and the same object is returned by ``read_*`` and ``list_*`` methods.
   This means that modifying the object outside of the mock changes the data stored inside the mock.

Testing error handling
----------------------

The ``mock_kubernetes`` fixture supports error injection by setting the ``error_callback`` attribute on the object to a callable.
If this is set, that callable will be called at the start of every mocked Kubernetes API call.
It will receive the method name as its first argument and the arguments to the method as its subsequent arguments.

Inside that callable, the test may, for example, make assertions about the arguments passed in to that method or raise exceptions to simulate errors from the Kubernetes API.

Here is a simplified example from `Gafaelfawr <https://gafaelfawr.lsst.io/>`__ that tests error handling for a command-line invocation when the Kubernetes API is not available:

.. code-block:: python

   def test_update_service_tokens_error(
       mock_kubernetes: MockKubernetesApi,
       caplog: LogCaptureFixture,
   ) -> None:
       caplog.clear()

       def error_callback(method: str, *args: Any) -> None:
           if method == "list_cluster_custom_object":
               raise ApiException(status=500, reason="Some error")

       mock_kubernetes.error_callback = error_callback
       runner = CliRunner()
       result = runner.invoke(main, ["update-service-tokens"])

       assert result.exit_code == 1
       assert parse_log(caplog) == [
           {
               "event": "Unable to list GafaelfawrServiceToken objects",
               "error": "Kubernetes API error: (500)\nReason: Some error\n",
               "severity": "error",
           },
       ]

Testing pod status
------------------

By default, any pod object created with `~safir.testing.kubernetes.MockKubernetesApi.create_namespaced_pod` gets an initial status of ``Running`` and generates a pod started event for its namespace (see :ref:`kubernetes-testing-events`).
This is done by modifying the pod object in place to add a status field.

To start pods in a different status, set the ``initial_pod_phase`` attribute of the Kubernetes mock to some other value.
If this is any value other than ``Running``, the pod startup event for the namespace will not be generated, so this also allows finer control of the events.

.. _kubernetes-testing-events:

Testing events
--------------

The only event that will be posted automatically by the mock Kubernetes API is a pod started event when creating a pod with `~safir.testing.kubernetes.MockKubernetesApi.create_namespaced_pod`, provided that the ``initial_pod_phase`` attribute on the mock is set to its default value of ``Running``.
All other events must be injected manually with `~safir.testing.kubernetes.MockKubernetesApi.create_namespaced_event`.

Testing node state
------------------

By default, the `~safir.testing.kubernetes.MockKubernetesApi.list_node` API returns an empty ``V1NodeList``.
A list of ``V1Node`` objects to return can be set by calling `~safir.testing.kubernetes.MockKubernetesApi.set_nodes_for_test`.

Comparing objects
-----------------

A good pattern to use when testing Kubernetes controllers is to store the Kubernetes objects expected to be created by a test case as data files in the test suite, and then compare the objects created inside the mock to the stored data files.
This, however, is complicated by the serialization format returned by the ``to_dict`` method of Kubernetes API objects.
Every possible field is included in the serialization, so the stored data and the pytest-generated diffs are littered with meaningless `None` values.

Safir provides the utility function `safir.testing.kubernetes.strip_none` to address this problem.
It takes a data structure with arbitrary nested lists and dictionaries, such as the output from ``to_dict``, and deletes all the dictionary keys whose value is `None`.
For Kubernetes objects, this is an equivalent but far more succinct canonical format, making comparisons easier.

Here is an example of how this function could be used in a test:

.. code-block:: python

   import json
   from pathlib import Path

   import pytest
   from safir.testing.kubernetes import MockKubernetesApi, strip_none


   @pytest.mark.asyncio
   async def test_controller(mock_kubernetes: MockKubernetesApi) -> None:
       # Take various test actions that would create a pod.
       pod = await mock_kubernetes.read_namespaced_pod("pod", "namespace")
       data_path = Path(__name__).parent / "data" / "pod.json"
       expected = json.loads(data_path.read_text())
       assert strip_none(pod.to_dict(serialize=True)) == expected

The data stored in :file:`tests/data/pod.json` can then contain only the interesting elements of the data model (the ones that are not `None`).

.. note::

   As in the above example, consider passing ``serialize=True`` whenever calling the ``to_dict`` method on a Kubernetes model.
   This tells the Kubernetes library to use the correct Kubernetes camel-case attribute names rather than the Python snake-case attribute names.

Performing actions after object creation
----------------------------------------

Safir supports registering a callback that is called after object creation.
To do this, call `~safir.testing.kubernetes.MockKubernetesApi.register_create_hook_for_test` with the kind of the object and the callback.
Whenever an object of that kind is created, the callback will be called.

This can be used to simulate such Kubernetes behavior as the creation of a default service account for a namespace, or assigning an IP address to an ingress.
