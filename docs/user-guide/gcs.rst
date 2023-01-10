##################################
Using the Google Cloud Storage API
##################################

Safir-based applications are encouraged to use the `google-cloud-storage <https://cloud.google.com/python/docs/reference/storage/latest>`__ Python module.
It provides both a sync and async API and works well with `workload identity <https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity>`__.

Google Cloud Storage support in Safir is optional.
To use it, depend on ``safir[gcs]``.

Testing with mock Google Cloud Storage
======================================

The `safir.testing.gcs` module provides a limited, mock Google Cloud Storage (GCS) API suitable for testing.
This mock provides just enough functionality to allow retrieving a bucket, retrieving a blob from the bucket, and creating a signed URL for the blob.

Applications that want to run tests with the mock GCS API should define a fixture (in ``conftest.py``) as follows:

.. code-block:: python

   from datetime import timedelta
   from typing import Iterator

   import pytest

   from safir.testing.gcs import MockStorageClient, patch_google_storage


   @pytest.fixture
   def mock_gcs() -> Iterator[MockStorageClient]:
       yield from patch_gcs(
           expected_expiration=timedelta(hours=1), bucket_name="some-bucket"
       )

The ``expected_expiration`` argument is mandatory and tells the mock object what expiration the application is expected to request for its signed URLs.
If the application, when tested, requests a signed URL with a different expiration, the mock will raise an assertion failure.

The ``bucket_name`` argument is optional.
If given, an attempt by the tested application to request a bucket of any other name will raise an assertion failure.

When this fixture is in use, the tested application can use Google Cloud Storage as normal, as long as it only makes the method calls supported by the mock object.
Some parameters to the method requesting a signed URL will be checked for expected values.
The returned signed URL will always be :samp:`https://example.com/{name}`, where the last component will be the requested blob name.
This can then be checked via assertions in tests.

To ensure that the mocking is done correctly, be sure not to import ``Client``, ``Credentials``, or similar symbols from ``google.cloud.storage`` or ``google.auth`` directly into a module.
Instead, use:

.. code-block:: python

   from google.cloud import storage

and then use, for example, ``storage.Client``.
