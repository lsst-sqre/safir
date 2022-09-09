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

   from safir.kubernetes import initialize_kubernetes


   @app.on_event("startup")
   async def startup_event() -> None:
       await initialize_kubernetes()

Testing with mock Kubernetes
============================

The `safir.testing.kubernetes` module provides a mock Kubernetes API with a limited implementation the API, and some utility functions to use it.

Applications that want to run tests with the mock Kubernetes API should define a fixture (in ``conftest.py``) as follows:

.. code-block:: python

   from typing import Iterator

   import pytest

   from safir.testing.kubernetes import MockKubernetesApi, patch_kubernetes


   @pytest.fixture
   def mock_kubernetes() -> Iterator[MockKubernetesApi]:
       yield from patch_kubernetes()

Then, when initializing Kubernetes, be sure not to import ``ApiClient``, ``CoreV1Api``, or ``CustomObjectsApi`` directly into a module.
Instead, use:

.. code-block:: python

   from kubernetes_asyncio import client

and then use ``client.ApiClient``, ``client.CoreV1Api``, and ``client.CustomObjectsApi``.
This will ensure that the Kubernetes API is mocked properly.

You can then use ``mock_kubernetes`` as a fixture.
The resulting object supports a limited subset of the ``client.CoreV1Api`` and ``client.CustomObjectsApi`` method calls for creating, retrieving, modifying, and deleting objects.
The objects created by either the test or by the application code under test will be stored in memory inside the ``mock_kubernetes`` object.

You can use the `~safir.testing.kubernetes.MockKubernetesApi.get_all_objects_for_test` method to retrieve all objects of a given kind, allowing comparisons against an expected list of objects.

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
