"""Retrieval of job results.

Job results are stored in a Google Cloud Storage bucket, but UWS requires they
be returned to the user as a URL. This translation layer converts the ``s3``
URL to a signed URL suitable for returning to a client of the service.
"""

from __future__ import annotations

try:
    from safir.gcs import SignedURLService
except ImportError as e:
    raise ImportError(
        "The safir.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e

from ._config import UWSConfig
from ._models import JobResult, SignedJobResult

__all__ = ["ResultStore"]


class ResultStore:
    """Result storage handling.

    Parameters
    ----------
    config
        The UWS configuration.
    """

    def __init__(self, config: UWSConfig) -> None:
        self._config = config
        self._url_service = SignedURLService(
            service_account=config.signing_service_account,
            lifetime=config.url_lifetime,
        )

    def sign_url(self, result: JobResult) -> SignedJobResult:
        """Convert a job result into a signed URL.

        Parameters
        ----------
        result
            Result with the URL from the backend.

        Returns
        -------
        SignedJobResult
            Result with any GCS URL replaced with a signed URL.

        Notes
        -----
        This uses custom credentials so that it will work with a GKE service
        account without having to export the secret key as a JSON blob and
        manage it as a secret. For more information, see `gcs_signedurl
        <https://github.com/salrashid123/gcs_signedurl>`__.

        This is probably too inefficient, since it gets new signing
        credentials each time it generates a signed URL. Doing better will
        require figuring out the lifetime and refreshing the credentials when
        the lifetime has expired, which in turn will probably require a
        longer-lived object to hold the credentials.
        """
        if result.url.startswith(("http", "https")):
            # Assume URL is already signed or otherwise directly usable.
            signed_url = result.url
        else:
            mime_type = result.mime_type
            signed_url = self._url_service.signed_url(result.url, mime_type)
        return SignedJobResult(
            id=result.id,
            url=signed_url,
            size=result.size,
            mime_type=result.mime_type,
        )
