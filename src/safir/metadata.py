"""Standardized metadata for Roundtable HTTP services.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

__all__ = ["get_metadata", "get_project_url"]


if sys.version_info < (3, 8):
    from importlib_metadata import metadata
else:
    from importlib.metadata import metadata

if TYPE_CHECKING:
    from typing import Any, Dict, Optional

    if sys.version_info < (3, 8):
        # mypy doesn't understand the PackageMetadata type returned by the
        # importlib_metadata backport supports dict operations.  In Python 3.8
        # and later, it's an email.message.Message, so declare it explicitly
        # as that type but alias that to Any on older versions.
        Message = Any
    else:
        from email.message import Message


def get_metadata(
    *, package_name: str, application_name: str, **kwargs: Any
) -> Dict[str, Optional[str]]:
    """Retrieve metadata for the application.

    Parameters
    ----------
    pacakge_name : `str`
        The name of the package (Python namespace). This name is used to look
        up metadata about the package.
    application_name : `str`
        The value to return as the application name (the ``name`` metadata
        field).
    **kwargs
        Add additional metadata keys, and their values, as keyword arguments.
        In practice, values must be JSON-serializable.

    Returns
    -------
    metadata : Dict[`str`, Optional[`str`]]
        The package metadata as a dictionary  For example:

        .. code-block:: python

           {
               "name": "safirdemo",
               "version": "0.1.0",
               "description": "Demonstration of a Safir-based app.",
               "repository_url": "https://github.com/lsst-sqre/safirdemo",
               "documentation_url": "https://github.com/lsst-sqre/safirdemo",
           }

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
    meta: Dict[str, Optional[str]] = {
        # Use provided name in case it is dynamically changed.
        "name": application_name,
        # Get metadata from the package configuration
        "version": pkg_metadata.get("Version", "0.0.0"),
        "description": pkg_metadata.get("Summary", None),
        "repository_url": get_project_url(pkg_metadata, "Source code"),
        "documentation_url": pkg_metadata.get("Home-page", None),
    }
    meta.update(**kwargs)
    return meta


def get_project_url(meta: Message, label: str) -> Optional[str]:
    """Get a specific URL from the ``project_urls`` key of a package's
    metadata.

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
