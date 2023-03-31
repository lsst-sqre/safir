##################################
Using the Google Cloud Storage API
##################################

Safir-based applications are encouraged to use the `google-cloud-storage <https://cloud.google.com/python/docs/reference/storage/latest>`__ Python module.
It provides both a sync and async API and works well with `workload identity <https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity>`__.

Google Cloud Storage support in Safir is optional.
To use it, depend on ``safir[gcs]``.

Generating signed URLs
======================

The preferred way to generate signed URLs for Google Cloud Storage objects is to use workload identity for the running pod, assign it a Kubernetes service account bound to a Google Cloud service account, and set appropriate permissions on that Google Cloud service account.

The credentials provided by workload identity cannot be used to sign URLs directly.
Instead, one first has to get impersonation credentials for the same service account, and then use those to sign the URL.
`safir.gcs.SignedURLService` automates this process.

To use this class, the workload identity of the running pod must have ``roles/iam.serviceAccountTokenCreator`` for a Google service account, and that service account must have appropriate GCS permissions for the object for which one wants to create a signed URL.
Then, do the following:

.. code-block:: python

   from datetime import timedelta

   from safir.gcs import SignedURLService


   url_service = SignedURLService("service-account")
   url = url_service.signed_url("s3://bucket/path/to/file", "application/fits")

The argument to the constructor is the name of the Google Cloud service account that will be used to sign the URLs.
This should be the one for which the workload identity has impersonation permissions.
(Generally, this should be the same service account to which the workload identity is bound.)

Optionally, you can specify the lifetime of the signed URLs as a second argument, which should be a `datetime.timedelta`.
If not given, the default is one hour.

The path to the Google Cloud Storage object for which to create a signed URL must be an S3 URL.
The second argument to `~safir.gcs.SignedURLService.signed_url` is the MIME type of the underlying object, which will be encoded in the signed URL.

Testing with mock Google Cloud Storage
======================================

The `safir.testing.gcs` module provides a limited, mock Google Cloud Storage (GCS) API suitable for testing.
By default, this mock provides just enough functionality to allow retrieving a bucket, retrieving a blob from the bucket, and creating a signed URL for the blob.
If a path to a tree of files is given, it can also mock some other blob attributes and methods based on the underlying files.

Testing signed URLs
-------------------

Applications that want to run tests with the mock GCS API should define a fixture (in ``conftest.py``) as follows:

.. code-block:: python

   from collections.abc import Iterator
   from datetime import timedelta

   import pytest
   from safir.testing.gcs import MockStorageClient, patch_google_storage


   @pytest.fixture
   def mock_gcs() -> Iterator[MockStorageClient]:
       yield from patch_google_storage(
           expected_expiration=timedelta(hours=1), bucket_name="some-bucket"
       )

The ``expected_expiration`` argument is optional and tells the mock object what expiration the application is expected to request for its signed URLs.
If this option is given and the application, when tested, requests a signed URL with a different expiration, the mock will raise an assertion failure.

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

Testing with a tree of files
----------------------------

To mock additional blob attributes and methods, point the test fixture at a tree of files with the ``path`` parameter.

.. code-block:: python
   :emphasize-lines: 1, 7

   from pathlib import Path


   @pytest.fixture
   def mock_gcs() -> Iterator[MockStorageClient]:
       yield from patch_google_storage(
           path=Path(__file__).parent / "data" / "files",
           expected_expiration=timedelta(hours=1),
           bucket_name="some-bucket",
       )

The resulting blobs will then correspond to the files on disk and will support the additional attributes ``size``, ``updated``, and ``etag``, and the additional methods ``download_as_bytes``, ``exists``, ``open``, and ``reload`` (which does nothing).
The Etag value of the blob will be the string version of its inode number.

Mock signed URLs will continue to work exactly the same as when a path is not provided.
