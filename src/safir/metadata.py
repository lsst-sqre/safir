"""Standardized metadata for Roundtable HTTP services.
"""

from __future__ import annotations

from importlib.metadata import metadata
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from email.message import Message

__all__ = ["Metadata", "get_metadata", "get_project_url"]


class Metadata(BaseModel):
    """Metadata about a package."""

    name: str = Field(..., title="Application name", example="myapp")

    version: str = Field(..., title="Version", example="1.0.0")

    description: Optional[str] = Field(
        None, title="Description", example="string"
    )

    repository_url: Optional[str] = Field(
        None, title="Repository URL", example="https://example.com/"
    )

    documentation_url: Optional[str] = Field(
        None, title="Documentation URL", example="https://example.com/"
    )


def get_metadata(*, package_name: str, application_name: str) -> Metadata:
    """Retrieve metadata for the application.

    Parameters
    ----------
    pacakge_name : `str`
        The name of the package (Python namespace). This name is used to look
        up metadata about the package.
    application_name : `str`
        The value to return as the application name (the ``name`` metadata
        field).

    Returns
    -------
    metadata : `Metadata`
        The package metadata as a Pydantic model, suitable for returning as
        the result of a FastAPI route.

    Notes
    -----
    ``get_metadata`` integrates extensively with your package's metadata.
    Typically this metadata is either set in the ``setup.cfg`` or ``setup.py``
    file (for setuptools-based applications):

    version
        Used as the version metadata. This may be set automatically with
        ``setuptools_scm``.
    summary
        Use as the ``description`` metadata.
    url
        Used as the ``documentation_url`` metadata.
    project_urls, Source code
        Used as the ``respository_url``.
    """
    pkg_metadata: Message = metadata(package_name)
    return Metadata(
        name=application_name,
        version=pkg_metadata.get("Version", "0.0.0"),
        description=pkg_metadata.get("Summary", None),
        repository_url=get_project_url(pkg_metadata, "Source code"),
        documentation_url=pkg_metadata.get("Home-page", None),
    )


def get_project_url(meta: Message, label: str) -> Optional[str]:
    """Get a specific URL from a package's ``project_urls`` metadata.

    Parameters
    ----------
    meta : `email.message.Message`
        The package metadata, as returned by the
        ``importlib.metadata.metadata`` function.
    label : `str`
        The URL's label. Consider the follow snippet of a ``setup.cfg`` file:

        .. code-block:: ini

           project_urls =
               Change log = https://safir.lsst.io/changelog.html
               Source code = https://github.com/lsst-sqre/safir
               Issue tracker = https://github.com/lsst-sqre/safir/issues

        To get the ``https://github.com/lsst-sqre/safir`` URL, the label is
        ``Source code``.

    Returns
    -------
    url : `str` or `None`
        The URL. If the label is not found, the function returns `None`.

    Examples
    --------
    >>> from importlib_metadata import metadata
    >>> meta = metadata("safir")
    >>> get_project_url(meta, "Source code")
    'https://github.com/lsst-sqre/safir'
    """
    prefix = f"{label}, "
    for key, value in meta.items():
        if key == "Project-URL":
            if value.startswith(prefix):
                return value[len(prefix) :]
    return None
