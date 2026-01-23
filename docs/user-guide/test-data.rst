.. py:currentmodule:: safir.testing.data

###############
Using test data
###############

Python application and library tests that contain long strings of expected results or large and complex Python data structures in-line in the test code can be harder to read and harder to update for changes to the code under test.
Moving complex test inputs and expected outputs into separate files, either text or JSON, often makes the tests easier to read and the data easier to update.

Safir provides a module, :py:mod:`safir.testing.data`, to simplify use of test data files in pytest_ tests.
This module allows easy retrieval of test data from files, a short-cut to compare a test output with an expected value, and a facility to update the expected output after code changes.

.. _test-data-fixture:

Creating a data fixture
=======================

The recommended way to use this library is to create a fixture named ``data`` in :file:`tests/conftest.py` and then use it in all tests that need to load or compare against test data.
Generally this fixture will look like the following:

.. code-block:: python

   import os
   import pytest
   from pathlib import Path
   from safir.testing.data import Data


   def pytest_addoption(parser: pytest.Parser) -> None:
       parser.addoption(
           "--update-test-data",
           action="store_true",
           default=False,
           help="Overwrite expected test output with current results",
       )


   @pytest.fixture
   def data(request: pytest.FixtureRequest) -> Data:
       update = request.config.getoption("--update-test-data")
       return Data(Path(__file__).parent / "data", update_test_data=update)

This approach adds a new pytest_ option, ``--update-test-data``, which if passed to pytest will tell the library to update expected test outputs as the tests are run.
This is discussed further below.

Using the test data
===================

The provided `Data` class provides three methods for reading test inputs:

`Data.read_text`
    Returns `str` test data.

`Data.read_json`
    Returns test data as a basic Python data structure, parsed from data stored as JSON.

`Data.read_pydantic`
    Returns test data as a Pydantic model, parsed from data stored as JSON.

All of these methods take as an argument a path fragment, which is a path relative to whatever root was given to the `Data` object when it was created (conventionally :file:`tests/data`).
`~Data.read_json` and `~Data.read_pydantic` will automatically add a ``.json`` extension, so the extension should be omitted from the path fragment.
`~Data.read_pydantic` additionally takes the Pydantic model class into which to convert the test data.

Complex or frequently reused test inputs should be read using those methods.
To compare test outputs to expected values, use the corresponding methods `~Data.assert_text_matches`, `~Data.assert_json_matches`, and `~Data.assert_pydantic_matches`.
These methods take the observed output and a path fragment, load expected output from the file specified by that path fragment, and then assert equality.
The assertion is configured to use pytest's rich assertion rewriting, so it will provide a diff on inequality of complex structures.

Updating expected test outputs
==============================

If the ``update_test_data`` constructor argument for `Data` is `True`, all of the ``assert_*`` methods will replace the existing expected data with the data passed to that function.
If you use the :ref:`above fixture <test-data-fixture>`, you can do this by passing the argument ``--update-test-data`` to pytest.

For packages using nox_, one can run, for example:

.. prompt:: bash

   nox -s test -- --update-test-data

For packages using tox_, a typical invocation is similar:

.. prompt:: bash

   tox run -e py -- --update-test-data

Test code (or any other code) can also explicitly write strings, data structures, or Pydantic files (serialized to JSON) to test data files using the `~Data.write_text`, `~Data.write_json`, and `~Data.write_pydantic` methods.
This may be useful in temporary code converting existing tests to use external test data.

Creating initial test data
--------------------------

This method for updating test data can be used to create the initial test data for expected outputs.
Simply write the test, using the appropriate ``assert_*`` methods, ensure that the parent directories of any expected output files exist, and then run the test suite with test data updating enabled as described above.
The tests will write expected output files based on the observed output, which you can then review and add to Git.

Wildcards in test output
------------------------

The `~Data.read_json` and `~Data.assert_json_matches` methods (and only those methods, not the others) convert the special string ``"<ANY>"`` in a JSON value to the `unittest.mock.ANY` wildcard.
This can be used for fields that contain serialized timestamps, unique identifiers, or other values that change with every test run.

When creating the initial test data, run the tests with updates enabled and then edit the resulting JSON, replacing the values of any fields that should be wildcards with the special string ``"<ANY>"``.

When test data is updated by `~Data.assert_json_matches` or `~Data.write_json`, any fields that contained ``"<ANY>"`` wildcards in the previous stored data are replaced with the same wildcard before the new data is stored.
In other words, wildcards are preserved across data updates.

Adding more methods
===================

The `Data` class is designed to be subclassed by applications that have their own specific types of data that they want to load.
Applications that subclass `Data` should, by convention, put that code in :file:`tests/support/data.py` and name the resulting class ``ApplicationData`` (replacing ``Application`` with the name of the application).

When subclassing, try to follow the convention of adding ``read_*``, ``write_*``, and ``assert_matches_*`` methods for each new data type.
The latter two can be omitted if the data type is only used for test input, not expected output.

New methods should use the base methods to do the comparison and write the data.
This generally means that the new data type should be serialized as if it were being written out as JSON (but without encoding it in JSON) before comparison and then passed to `~Data.assert_json_matches`.
This ensures rich exception reports and a standard data format for the serialized data.
