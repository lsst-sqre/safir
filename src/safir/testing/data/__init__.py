"""Read and optionally update test data."""

try:
    import pytest

    pytest.register_assert_rewrite("safir.testing.data._data")
except ImportError as e:
    raise ImportError(
        "The safir.testing.data module requires pytest and should only"
        " be listed in the `dev` dependency group of a package"
    ) from e

from ._data import Data

__all__ = ["Data"]
