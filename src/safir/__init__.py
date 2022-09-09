"""Safir is the Rubin Observatory's library for building FastAPI services
for the Rubin Science Platform.
"""

__all__ = ["__version__", "version_info"]

from importlib.metadata import PackageNotFoundError, version

__version__: str
"""The version string of Safir (PEP 440 / SemVer compatible)."""

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # package is not installed
    __version__ = "0.0.0"

version_info = __version__.split(".")
"""The decomposed version, split across "``.``."

Use this for version comparison.
"""
