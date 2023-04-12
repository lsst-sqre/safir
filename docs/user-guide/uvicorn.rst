########################################
Starting an app with Uvicorn for testing
########################################

Normally, testing of FastAPI apps should be done by passing the app to ``httpx.AsyncClient`` and using HTTPX's built-in support for sending requests directly to an ASGI application.
To do this, use the ``client`` fixture provided by the ``fastapi_safir_app`` template (see :ref:`create-from-template`).

However, in some test scenarios it may be necessary for the app being tested to respond to regular HTTP requests, such as for Selenium_ testing with a browser.
Testing integration with Uvicorn_ also requires running the app with Uvicorn.

.. _Selenium: https://selenium-python.readthedocs.io/

`safir.testing.uvicorn.spawn_uvicorn` is a helper function to spawn a separate Uvicorn process to run a test FastAPI application.
The details about the running process are provided in a returned dataclass, `~safir.testing.uvicorn.UvicornProcess`.

To use this function, write a fixture similar to the following.
This code assumes the source code of the test app is in the variable ``_APP_SOURCE``, and that code declares a variable named ``app`` to hold the FastAPI object.

.. code-block:: python

   from collections.abc import Iterator

   from safir.testing.uvicorn import UvicornProcess, spawn_uvicorn


   @pytest.fixture
   def uvicorn(tmp_path: Path) -> Iterator[UvicornProcess]:
       app_path = tmp_path / "test.py"
       app_path.write_text(_APP_SOURCE)
       uvicorn = spawn_uvicorn(working_directory=tmp_path, app="test:app")
       yield process
       uvicorn.terminate()

The ``.url`` attribute of the returned object will contain the base URL of the running app.
It will be listening on localhost on a random high-numbered port.

Writing out small test files is useful for quick tests.
For more complex applications, the ``app`` argument can instead be any variable in any module on the Python search path that contains a FastAPI app to run.
Additional environment variables for the app can be passed via the ``env`` argument to `~safir.testing.uvicorn.spawn_uvicorn`.

Alternately, if you need to dynamically create the application (using other fixtures, for example), you can pass in a factory function:

.. code-block:: python
   :emphasize-lines: 10-13

   from collections.abc import Iterator

   from safir.testing.uvicorn import UvicornProcess, spawn_uvicorn


   @pytest.fixture
   def uvicorn(tmp_path: Path) -> Iterator[UvicornProcess]:
       app_path = tmp_path / "test.py"
       app_path.write_text(_APP_SOURCE)
       uvicorn = spawn_uvicorn(
           working_directory=tmp_path,
           factory="tests.support.selenium:create_app",
       )
       yield process
       uvicorn.process.terminate()

By default, the output from Uvicorn is sent to the normal standard output and standard error, where it will be captured by pytest but will not be available to the test.
If the test itself needs to inspect the Uvicorn output, pass ``capture=True`` to `~safir.testing.uvicorn.spawn_uvicorn`, and then call the `~subprocess.Popen.communicate` method on the ``.process`` attribute of the returned object to retrieve the standard output and standard error (generally after calling its `~subprocess.Popen.terminate` method).
For example:

.. code-block:: python

   import pytest
   from httpx import AsyncClient

   from safir.testing.uvicorn import UvicornProcess, spawn_uvicorn


   @pytest.mark.asyncio
   def test_something(tmp_path: Path) -> None:
       app_path = tmp_path / "test.py"
       app_path.write_text(_APP_SOURCE)
       uvicorn = spawn_uvicorn(
           working_directory=tmp_path,
           factory="tests.support.selenium:create_app",
           capture=True,
       )
       try:
           async with AsyncClient() as client:
               # Interact with app at uvicorn.url
               ...
       finally:
           uvicorn.process.terminate()
       stdout, stderr = uvicorn.process.communicate()

       # Do something with stdout and stderr
