"""Mocks and functions for testing services using the Safir UWS support."""

try:
    import pytest

    pytest.register_assert_rewrite("safir.testing.uws._assert")
    pytest.register_assert_rewrite("safir.testing.uws._mocks")
except ImportError as e:
    raise ImportError(
        "The safir.testing.uws module requires pytest and should only"
        " be listed in the `dev` dependency group of a package"
    ) from e

from ._assert import assert_job_summary_equal
from ._mocks import MockUWSJobRunner, MockWobbly, patch_wobbly

__all__ = [
    "MockUWSJobRunner",
    "MockWobbly",
    "assert_job_summary_equal",
    "patch_wobbly",
]
