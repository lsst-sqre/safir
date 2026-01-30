"""Read and optionally update test data."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from itertools import zip_longest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import ANY

from pydantic import BaseModel

if TYPE_CHECKING:
    from pyfakefs.fake_filesystem import FakeFilesystem

__all__ = ["Data"]


class Data:
    """Locate, read, and write test data.

    This class provides utility functions to load test data, compare test
    output against expected output stored in files, and optionally update
    stored data.

    Stored output data (as specified in ``assert_*`` methods) will be updated
    (and thus the ``assert_*`` methods will never fail) if the
    ``update_test_data`` constructor argument is `True`. Generally this should
    be set by the fixture if the environment variable ``UPDATE_TEST_DATA`` is
    set.

    Applications are actively encouraged to subclass this class to add more
    specific ``read_*``, ``write_*``, and ``assert_*`` methods that are
    specific to the data types used by that application. Those methods should
    call the methods provided by this base class to perform lower-level
    operations. In particular, convert objects to JSON and use
    `assert_json_matches` or `assert_pydantic_matches` to compare them so that
    stored output data updating is properly supported.

    Parameters
    ----------
    root
        Path to the root of the test data. Generally this will be discovered
        based on the path to the :file:`conftest.py` from which this class
        is initialized.
    fake_filesystem
        If given, the currently active fake filesystem object from pyfakefs.
        This fake filesystem will be paused during writes so that updating
        test data will still work for tests that use a fake filesystem.
    update_test_data
        Whether to overwrite expected output in ``assert_*`` methods.

    Examples
    --------
    This class is generally created and returned by a fixture in
    :file:`tests/conftest.py` such as the following:

    .. code-block:: python

       import os
       from pathlib import Path
       from safir.testing.data import Data


       @pytest.fixture
       def data() -> Data:
           update = bool(os.getenv("UPDATE_TEST_PATH"))
           return Data(Path(__file__).parent / "data", update_test_data=update)
    """

    def __init__(
        self,
        root: Path,
        *,
        fake_filesystem: "FakeFilesystem | None" = None,
        update_test_data: bool = False,
    ) -> None:
        self._fake_fs = fake_filesystem
        self._root = root
        self._update = update_test_data

    def assert_json_matches(self, seen: Any, path: str) -> None:
        """Raise an assertion if the saved expected output doesn't match.

        ``<ANY>`` strings in the saved expected output are converted to the
        `unittest.mock.ANY` wildcard before comparison.

        Parameters
        ----------
        seen
            Observed data in the test to be compared.
        path
            Path relative to :file:`tests/data` of the expected output. A
            ``.json`` extension will be added automatically.

        Raises
        ------
        AssertionError
            Raised if the data doesn't match.
        """
        if self._update:
            self.write_json(seen, path)
        assert seen == self.read_json(path)

    def assert_pydantic_matches(self, seen: BaseModel, path: str) -> None:
        """Raise an assertion if the saved Pydantic model doesn't match.

        The Pydantic model is serialized to JSON and then compared against the
        stored JSON serialization, since that produces a better rich diff on
        mismatch.

        This method will miss differences that are not part of the JSON
        serialization of the model, and only models that can be serialized to
        JSON can be compared.

        Parameters
        ----------
        seen
            Any Pydantic model. The saved data will be presumed to be for the
            same model.
        path
            Path relative to :file:`tests/data` of the expected output. A
            ``.json`` extension will be added automatically.

        Raises
        ------
        AssertionError
            Raised if the data doesn't match.
        """
        if self._update:
            self.write_pydantic(seen, path)
        assert seen.model_dump(mode="json") == self.read_json(path)

    def assert_text_matches(self, seen: str, path: str) -> None:
        """Raise an assertion if the saved expected output doesn't match.

        Parameters
        ----------
        seen
            Observed data in the test to be compared.
        path
            Path relative to :file:`tests/data` of the expected output.

        Raises
        ------
        AssertionError
            Raised if the data doesn't match.
        """
        if self._update:
            self.write_text(seen, path)
        assert seen == self.read_text(path)

    def path(self, path: str, extension: str | None = None) -> Path:
        """Construct a path to a test data file.

        Parameters
        ----------
        path
            Path relative to :file:`tests/data`.
        extension
            Optional extension to add to the file name. If set, the extension
            will be preceded by a period (``.``).

        Returns
        -------
        pathlib.Path
            Full path to file.
        """
        if extension is not None:
            path += f".{extension}"
        return self._root / path

    def read_json(self, path: str) -> Any:
        """Read test data as JSON and return its decoded form.

        ``<ANY>`` strings in the saved expected output are converted to the
        `unittest.mock.ANY` wildcard.

        Parameters
        ----------
        path
            Path relative to :file:`tests/data`. A ``.json`` extension will be
            added automatically.

        Returns
        -------
        typing.Any
            Parsed contents of the file.
        """
        with self.path(path, "json").open("r") as f:
            return self._convert_any(json.load(f))

    def read_pydantic[T: BaseModel](self, model_type: type[T], path: str) -> T:
        """Read test data as a Pydantic model.

        Parameters
        ----------
        path
            Path relative to :file:`tests/data`. A ``.json`` extension will be
            added automatically.

        Returns
        -------
        pydantic.BaseModel
            Contents of the file validated as a Pydantic model of the given
            type.
        """
        return model_type.model_validate(self.read_json(path))

    def read_text(self, path: str) -> str:
        """Read test data as text.

        Parameters
        ----------
        path
            Path relative to :file:`tests/data`.

        Returns
        -------
        str
            Contents of file.
        """
        return self.path(path).read_text()

    def write_json(self, data: Any, path: str) -> None:
        """Write data as JSON to the test data directory.

        Parameters
        ----------
        data
            New data to write.
        path
            Path relative to :file:`tests/data` of the expected output. A
            ``.json`` extension will be added automatically.
        """
        with self._pause_fake_fs():
            if self.path(path, "json").exists():
                data = self._copy_wildcards(data, self.read_json(path))
            with self.path(path, "json").open("w") as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.write("\n")

    def write_pydantic(self, data: BaseModel, path: str) -> None:
        """Write a Pydantic model as JSON to the test data directory.

        Parameters
        ----------
        data
            Pydantic model to write.
        path
            Path relative to :file:`tests/data` of the expected output. A
            ``.json`` extension will be added automatically.
        """
        self.write_json(data.model_dump(mode="json"), path)

    def write_text(self, data: str, path: str) -> None:
        """Write data as text to the test data directory.

        Parameters
        ----------
        data
            New data to write.
        path
            Path relative to :file:`tests/data` of the expected output.
        """
        with self._pause_fake_fs():
            self.path(path).write_text(data)

    def _copy_wildcards(self, new: Any, old: Any) -> Any:
        """Recursively copy `unittest.mock.ANY` wildcards to new data.

        Where there is a `unittest.mock.ANY` in the old data, replace the new
        data with the special string ``<ANY>``, which will be replaced with
        the same wildcard on reading.

        Parameters
        ----------
        new
            New data as a native Python data structure (not Pydantic models
            or dataclasses).
        old
            Old data, which may contain wildcards.

        Returns
        -------
        typing.Any
            The same data with any fields that were wildcards in the old data
            replaced with wildcards in the new data.
        """
        if type(old) is type(ANY):
            return "<ANY>"
        match new:
            case list():
                if not isinstance(old, list):
                    return list(new)
                if len(old) > len(new):
                    old = old[: len(new)]
                return [
                    self._copy_wildcards(n, o)
                    for n, o in zip_longest(new, old, fillvalue=None)
                ]
            case dict():
                if not isinstance(old, dict):
                    return dict(new)
                return {
                    k: self._copy_wildcards(v, old.get(k))
                    for k, v in new.items()
                }
            case _:
                return new

    def _convert_any(self, data: Any) -> Any:
        """Recursively convert ``<ANY>`` to `unittest.mock.ANY`.

        Parameters
        ----------
        data
            Input data as a native Python data structure (not Pydantic models
            or dataclasses).

        Returns
        -------
        typing.Any
            The same data with ``<ANY>`` strings converted.
        """
        match data:
            case list():
                return [self._convert_any(e) for e in data]
            case dict():
                return {k: self._convert_any(v) for k, v in data.items()}
            case "<ANY>":
                return ANY
            case _:
                return data

    @contextmanager
    def _pause_fake_fs(self) -> Iterator[None]:
        """Pause any fake file system from pyfakefs.

        Used as a context manager around write operations that should write to
        the real underlying file system, not to any fake file system
        maintained by pyfakefs. The ``_root`` `~pathlib.Path` object has to be
        recreated when pausing or unpausing the fake file system to correctly
        switch from fake to real and back.
        """
        if self._fake_fs:
            self._fake_fs.pause()
            self._root = Path(str(self._root))
        yield
        if self._fake_fs:
            self._fake_fs.resume()
            self._root = Path(str(self._root))
