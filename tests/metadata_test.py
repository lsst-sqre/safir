"""Tests for the safir.metadata module.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from safir.metadata import get_metadata, get_project_url

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
        from typing import Any

        Message = Any
    else:
        from email.message import Message


@pytest.fixture(scope="session")
def safir_metadata() -> Message:
    return metadata("safir")


def test_get_project_url(safir_metadata: Message) -> None:
    """Test the get_project_url function using Safir's own metadata."""
    source_url = get_project_url(safir_metadata, "Source code")
    assert source_url == "https://github.com/lsst-sqre/safir"


def test_get_project_url_missing(safir_metadata: Message) -> None:
    """Test that get_project_url returns None for a missing URL."""
    source_url = get_project_url(safir_metadata, "Nonexistent")
    assert source_url is None


async def test_get_metadata() -> None:
    """Test get_metadata in normal usage."""
    data = get_metadata(package_name="safir", application_name="testapp")
    assert data["name"] == "testapp"
    assert "version" in data
    assert "description" in data
    assert data["repository_url"] == "https://github.com/lsst-sqre/safir"
    assert data["documentation_url"] == "https://safir.lsst.io"
