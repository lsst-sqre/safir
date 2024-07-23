"""Standardized metadata for Roundtable HTTP services."""

from __future__ import annotations

from email.message import Message
from importlib.metadata import metadata
from typing import cast

from pydantic import BaseModel, Field

__all__ = ["Metadata", "get_metadata", "get_project_url"]


class Metadata(BaseModel):
    """Metadata about a package."""

    name: str = Field(..., title="Application name", examples=["myapp"])

    version: str = Field(..., title="Version", examples=["1.0.0"])

    description: str | None = Field(
        None, title="Description", examples=["Some package description"]
    )

    repository_url: str | None = Field(
        None, title="Repository URL", examples=["https://example.com/"]
    )

    documentation_url: str | None = Field(
        None, title="Documentation URL", examples=["https://example.com/"]
    )


def get_metadata(*, package_name: str, application_name: str) -> Metadata:
    """Retrieve metadata for the application.

    Parameters
    ----------
    pacakge_name
        The name of the package (Python namespace). This name is used to look
        up metadata about the package.
    application_name
        The value to return as the application name (the ``name`` metadata
        field).

    Returns
    -------
    Metadata
        The package metadata as a Pydantic model, suitable for returning as
        the result of a FastAPI route.

    Notes
    -----
    ``get_metadata`` integrates extensively with your package's metadata.
    Typically this metadata is set in ``pyproject.toml``, ``setup.cfg``,
    ``setup.py`` file (for setuptools-based applications).  The
    ``pyproject.toml`` fields used are:

    version
        Used as the version metadata. This may be set automatically with
        ``setuptools_scm``.
    description
        Use as the ``description`` metadata.
    project.urls, Homepage
        Used as the ``documentation_url`` metadata.
    project.urls, Source
        Used as the ``respository_url``.

    Packages using ``setup.cfg`` or ``setup.py`` get the last three items of
    metadata from different sources:

    summary
        Use as the ``description`` metadata.
    url
        Used as the ``documentation_url`` metadata.
    project_urls, Source code
        Used as the ``respository_url``.
    """
    pkg_metadata = cast(Message, metadata(package_name))

    # Newer packages that use pyproject.toml only do not use the Home-page
    # field (setuptools in pyproject.toml mode does not support it) and use
    # different names for the project URLs.  Attempt those names first and
    # fall back to the older names.
    repository_url = get_project_url(pkg_metadata, "Source")
    if not repository_url:
        repository_url = get_project_url(pkg_metadata, "Source code")
    documentation_url = get_project_url(pkg_metadata, "Homepage")
    if not documentation_url:
        documentation_url = pkg_metadata.get("Home-page", None)

    return Metadata(
        name=application_name,
        version=pkg_metadata.get("Version", "0.0.0"),
        description=pkg_metadata.get("Summary", None),
        repository_url=repository_url,
        documentation_url=documentation_url,
    )


def get_project_url(meta: Message, label: str) -> str | None:
    """Get a specific URL from a package's ``project_urls`` metadata.

    Parameters
    ----------
    meta
        The package metadata, as returned by the
        ``importlib.metadata.metadata`` function.
    label
        The URL's label. Consider the follow snippet of a ``pyproject.toml``
        file:

        .. code-block:: toml

           [project.urls]
           Homepage = "https://safir.lsst.io/"
           Source = "https://github.com/lsst-sqre/safir"

        To get the ``https://github.com/lsst-sqre/safir`` URL, the label is
        ``Source``.

        Packages using ``setup.cfg`` use a different syntax but a similar
        approach.

        .. code-block:: ini

           project_urls =
               Change log = https://safir.lsst.io/changelog.html
               Source code = https://github.com/lsst-sqre/safir
               Issue tracker = https://github.com/lsst-sqre/safir/issues

        To get the ``https://github.com/lsst-sqre/safir`` URL, the label is
        ``Source code``.

    Returns
    -------
    str or None
        The URL. If the label is not found, the function returns `None`.

    Examples
    --------
    >>> from importlib_metadata import metadata
    >>> meta = metadata("safir")
    >>> get_project_url(meta, "Source")
    'https://github.com/lsst-sqre/safir'
    """
    prefix = f"{label}, "
    for key, value in meta.items():
        if key == "Project-URL":
            if value.startswith(prefix):
                return value[len(prefix) :]
    return None
