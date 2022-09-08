"""Tests for the safir.metadata module.
"""

from __future__ import annotations

import sys
from email.message import Message
from importlib.metadata import metadata
from typing import cast

import pytest

from safir.metadata import get_metadata, get_project_url


@pytest.fixture(scope="session")
def safir_metadata() -> Message:
    if sys.version_info >= (3, 10):
        return cast(Message, metadata("safir"))
    else:
        return metadata("safir")


def test_get_project_url(safir_metadata: Message) -> None:
    """Test the get_project_url function using Safir's own metadata."""
    source_url = get_project_url(safir_metadata, "Source")
    assert source_url == "https://github.com/lsst-sqre/safir"


def test_get_project_url_missing(safir_metadata: Message) -> None:
    """Test that get_project_url returns None for a missing URL."""
    source_url = get_project_url(safir_metadata, "Nonexistent")
    assert source_url is None


@pytest.mark.asyncio
async def test_get_metadata() -> None:
    """Test get_metadata in normal usage."""
    data = get_metadata(package_name="safir", application_name="testapp")
    assert data.name == "testapp"
    assert data.version
    assert data.description
    assert data.repository_url == "https://github.com/lsst-sqre/safir"
    assert data.documentation_url == "https://safir.lsst.io"
