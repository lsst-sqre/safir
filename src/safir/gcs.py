"""Utilities for interacting with Google Cloud Storage."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlparse

import google.auth
from google.auth import impersonated_credentials
from google.cloud import storage

__all__ = ["SignedURLService"]


class SignedURLService:
    """Generate signed URLs for Google Cloud Storage blobs.

    Uses default credentials plus credential impersonation to generate signed
    URLs for Google Cloud Storage blobs.  This is the correct approach when
    running as a Kubernetes pod using workload identity.

    Parameters
    ----------
    service_account
        The service account to use to sign the URLs.  The workload identity
        must have access to generate service account tokens for that service
        account.
    lifetime
        Lifetime of the generated signed URLs.

    Notes
    -----
    The workload identity (or other default credentials) under which the
    caller is running must have ``roles/iam.serviceAccountTokenCreator`` on
    the service account given in the ``service_account`` parameter.  This is
    how a workload identity can retrieve a key that can be used to create a
    signed URL.

    See `gcs_signedurl <https://github.com/salrashid123/gcs_signedurl>`__ for
    additional details on how this works.
    """

    def __init__(
        self, service_account: str, lifetime: timedelta = timedelta(hours=1)
    ) -> None:
        self._lifetime = lifetime
        self._service_account = service_account
        self._gcs = storage.Client()
        self._credentials, _ = google.auth.default()

    def signed_url(self, uri: str, mime_type: str | None) -> str:
        """Generate signed URL for a given storage object.

        Parameters
        ----------
        uri
            URI for the storage object.  This must start with ``s3://`` and
            use the S3 URI syntax to specify bucket and blob of a Google
            Cloud Storage object.
        mime_type
            MIME type of the object, for encoding in the signed URL.

        Returns
        -------
        str
            New signed URL, which will be valid for as long as the lifetime
            parameter to the object.

        Raises
        ------
        ValueError
            The ``uri`` parameter is not an S3 URI.

        Notes
        -----
        This is inefficient, since it gets new signing credentials each time
        it generates a signed URL.  Doing better will require figuring out the
        lifetime and refreshing the credentials when the lifetime has expired.
        """
        parsed_uri = urlparse(uri)
        if parsed_uri.scheme != "s3":
            raise ValueError(f"URI {uri} is not an S3 URI")
        bucket = self._gcs.bucket(parsed_uri.netloc)
        blob = bucket.blob(parsed_uri.path[1:])
        signing_credentials = impersonated_credentials.Credentials(
            source_credentials=self._credentials,
            target_principal=self._service_account,
            target_scopes=(
                "https://www.googleapis.com/auth/devstorage.read_only"
            ),
            lifetime=2,
        )
        return blob.generate_signed_url(
            version="v4",
            expiration=self._lifetime,
            method="GET",
            response_type=mime_type,
            credentials=signing_credentials,
        )
