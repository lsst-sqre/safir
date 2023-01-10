"""Mock Google Cloud Storage API for testing."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterator, Optional
from unittest.mock import Mock, patch

from google.cloud import storage

__all__ = [
    "MockBlob",
    "MockBucket",
    "MockStorageClient",
    "patch_google_storage",
]


class MockBlob(Mock):
    """Mock version of ``google.cloud.storage.blob.Blob``.

    Parameters
    ----------
    name
        Name of the blob.
    expected_expiration
        The expiration that should be requested in a call to
        ``generate_signed_url`` on an underlying blob.  A non-matching call
        will produce an assertion failure.
    """

    def __init__(self, name: str, expected_expiration: timedelta) -> None:
        super().__init__(spec=storage.blob.Blob)
        self.name = name
        self._expected_expiration = expected_expiration

    def generate_signed_url(
        self,
        *,
        version: str,
        expiration: timedelta,
        method: str,
        response_type: Optional[str] = None,
        credentials: Optional[Any] = None,
    ) -> str:
        """Generate a mock signed URL for testing.

        Parameters
        ----------
        version
            Must be ``v4``.
        expiration
            Must match the ``expected_expiration`` argument to the
            constructor.
        method
            Must be ``GET``.
        response_type
            May be anything and is ignored.
        credentials
            May be anything and is ignored.

        Returns
        -------
        str
            Always returns :samp:`https://example.com/{name}` where *name* is
            the name of the blob.
        """
        assert version == "v4"
        assert expiration == self._expected_expiration
        assert method == "GET"
        return f"https://example.com/{self.name}"


class MockBucket(Mock):
    """Mock version of ``google.cloud.storage.bucket.Bucket``.

    Parameters
    ----------
    expected_expiration
        The expiration that should be requested in a call to
        ``generate_signed_url`` on an underlying blob.  A non-matching call
        will produce an assertion failure.
    """

    def __init__(
        self, bucket_name: str, expected_expiration: timedelta
    ) -> None:
        super().__init__(spec=storage.bucket.Bucket)
        self._expected_expiration = expected_expiration

    def blob(self, blob_name: str) -> MockBlob:
        """Retrieve a mock blob.

        Parameters
        ----------
        blob_name
            The name of the blob, used later to form its signed URL.

        Returns
        -------
        MockBlob
            The mock blob.
        """
        return MockBlob(blob_name, self._expected_expiration)


class MockStorageClient(Mock):
    """Mock version of ``google.cloud.storage.Client``.

    Only supports `bucket`, and the resulting object only supports the
    ``blob`` method.  The resulting blob only supports the
    ``generate_signed_url`` method.

    Parameters
    ----------
    expected_expiration
        The expiration that should be requested in a call to
        ``generate_signed_url`` on an underlying blob.  A non-matching call
        will produce an assertion failure.
    bucket_name
        If set, all requests for a bucket with a name other than the one
        provided will produce assertion failures.
    """

    def __init__(
        self,
        expected_expiration: timedelta,
        bucket_name: Optional[str] = None,
    ) -> None:
        super().__init__(spec=storage.Client)
        self._bucket_name = bucket_name
        self._expected_expiration = expected_expiration

    def bucket(self, bucket_name: str) -> MockBucket:
        """Retrieve a mock bucket.

        Parameters
        ----------
        bucket_name
            Name of the bucket.  If a bucket name was given to the
            constructor, this name will be checked against that one and a
            mismatch will cause an assertion failure.

        Returns
        -------
        MockBucket
            The mock bucket.
        """
        if self._bucket_name:
            assert bucket_name == self._bucket_name
        return MockBucket(bucket_name, self._expected_expiration)


def patch_google_storage(
    *, expected_expiration: timedelta, bucket_name: Optional[str] = None
) -> Iterator[MockStorageClient]:
    """Replace the Google Cloud Storage API with a mock class.

    This function will replace the ``google.cloud.storage.Client`` API with a
    mock object.  It only supports bucket requests, the buckets only support
    blob requests, and the blobs only support requests for signed URLs.  The
    value of the signed URL will be :samp:`https://example.com/{blob}` where
    *blob* is the name of the blob.

    Yields
    ------
    MockStorageClient
        The mock Google Cloud Storage API client (although this is rarely
        needed by the caller).

    Parameters
    ----------
    expected_expiration
        The expiration that should be requested in a call to
        ``generate_signed_url`` on an underlying blob.  A non-matching call
        will produce an assertion failure.
    bucket_name
        If set, all requests for a bucket with a name other than the one
        provided will produce assertion failures.

    Notes
    -----
    This function also mocks out ``google.auth.default`` and the impersonated
    credentials structure so that this mock can be used with applications that
    use workload identity.

    To use this mock successfully, you must not import ``Client`` (or
    ``Credentials``) directly into the local namespace, or it will not be
    correctly patched.  Instead, use:

    .. code-block:: python

       from google.cloud import storage

    and then use ``storage.Client`` and so forth.  Do the same with
    q`google.auth.impersonated_credentials.Credentials``.

    Examples
    --------
    Normally this should be called from a fixture in ``tests/conftest.py``
    such as the following:

    .. code-block:: python

       from datetime import timedelta

       from safir.testing.gcs import MockStorageClient, patch_google_storage


       @pytest.fixture
       def mock_gcs() -> Iterator[MockStorageClient]:
           yield from patch_gcs(
               expected_expiration=timedelta(hours=1),
               bucket_name="some-bucket",
           )
    """
    mock_gcs = MockStorageClient(expected_expiration, bucket_name)
    with patch("google.auth.impersonated_credentials.Credentials"):
        with patch("google.auth.default", return_value=(None, None)):
            with patch("google.cloud.storage.Client", return_value=mock_gcs):
                yield mock_gcs
