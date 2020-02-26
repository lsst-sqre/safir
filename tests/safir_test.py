"""Tests for safir, the top-level import."""

import safir


def test_version() -> None:
    assert isinstance(safir.__version__, str)
    assert isinstance(safir.version_info, list)
