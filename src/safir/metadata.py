"""Standardized metadata for Roundtable HTTP services.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Dict, Optional

from aiohttp import web

__all__ = ["setup_metadata", "get_project_url"]


if sys.version_info < (3, 8):
    from importlib_metadata import metadata
else:
    from importlib.metadata import metadata

if TYPE_CHECKING:
    if sys.version_info < (3, 8):
        # mypy doesn't understand the PackageMetadata type returned by the
        # importlib_metadata backport supports dict operations.  In Python 3.8
        # and later, it's an email.message.Message, so declare it explicitly
        # as that type but alias that to Any on older versions.
        Message = Any
    else:
        from email.message import Message


def setup_metadata(
    *, package_name: str, app: web.Application, **kwargs: Any
) -> None:
    """Add a metadata object to the application under the ``safir/metadata``
    key.

    Parameters
    ----------
    pacakge_name : `str`
        The name of the package (Python namespace). This name is used to look
        up metadata about the package.
    app : `aiohttp.web.Application`
        The application, which must already have a standard configuration
        object at the ``safir/config`` key. This function uses the ``name``
        attribute of the configuration.
    **kwargs
        Add additional metadata keys, and their values, as keyword arguments.
        In practice, values must be JSON-serializable.

    Notes
    -----
    **Metadata sources**

    ``setup_metadata`` integrates extensively with your package's metadata.
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

    The configuration object (``app["safir/config"]``) also provides metadata:

    config.name
        Used as the ``name`` metadata field.

    **Metadata schema**

    The metadata is stored as a `dict` in the ``"safir/metadata"`` key of the
    application:

    .. code-block:: json

       {
         "name": "safirdemo",
         "version": "0.1.0",
         "description": "Demonstration of a Safir-based app.",
         "repository_url": "https://github.com/lsst-sqre/safirdemo",
         "documentation_url": "https://github.com/lsst-sqre/safirdemo"
       }
    """
    pkg_metadata: Message = metadata(package_name)

    try:
        config = app["safir/config"]
    except KeyError:
        raise RuntimeError(
            "Application does not have a 'safir/config' key. "
            "Add configuration to the application before running "
            "setup_metadata."
        )

    meta: Dict[str, Any] = {
        # Use configured name in case it is dynamically changed.
        "name": config.name,
        # Get metadata from the package configuration
        "version": pkg_metadata.get("Version", "0.0.0"),
        "description": pkg_metadata.get("Summary", None),
        "repository_url": get_project_url(pkg_metadata, "Source code"),
        "documentation_url": pkg_metadata.get("Home-page", None),
    }
    meta.update(**kwargs)
    app["safir/metadata"] = meta


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
