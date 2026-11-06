#######################
Using the HTTPX2 client
#######################

Safir helps you manage a single ``httpx2.AsyncClient`` for your application.
Using a single HTTPX2_ client improves performance by reusing connections.

Setting up the httpx2.AsyncClient
=================================

The ``httpx2.AsyncClient`` will be dyanmically created during application startup.
Nothing further is needed apart from importing the dependency.
However, it must be closed during application shutdown or a warning will be generated.
This is normally done during the lifespan function for the FastAPI app.

.. code-block:: python

   from collections.abc import AsyncGenerator
   from contextlib import asynccontextmanager

   from safir.dependencies.http_client import http_client_dependency


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
       yield
       await http_client_dependency.aclose()


   app = FastAPI(lifespan=lifespan)

You can add this line to an existing shutdown hook if you already have one.

Using the httpx2.AsyncClient
============================

To use the client in a handler, just request it via a FastAPI dependency:

.. code-block:: python

   from typing import Annotated

   from httpx2 import AsyncClient
   from safir.dependencies.http_client import http_client_dependency


   @routes.get("/")
   async def get_index(
       http_client: Annotated[AsyncClient, Depends(http_client_dependency)],
   ) -> Dict[str, Any]:
       response = await http_client.get("https://keeper.lsst.codes")
       return await response.json()

Testing considerations
======================

Startup and shutdown
--------------------

If you are using ``httpx2.AsyncClient`` in your application tests as well, note that it will not trigger shutdown events, so if you trigger handlers that use the HTTP client, you will get a warning about an unclosed ``httpx2.AsyncClient`` in your test output.
To avoid this, wrap your test application in ``asgi_lifespan.LifespanManager`` from the asgi-lifespan Python package:

.. code-block:: python

   app = FastAPI()
   async with LifespanManager(app):
       # insert tests here
       pass

You can do this in a yield fixture to avoid code duplication.

.. code-block:: python

   from yourapp import main


   @pytest_asyncio.fixture
   async def app() -> AsyncGenerator[FastAPI]:
       # Add any other necessary application setup here.
       async with LifespanManager(main.app):
           yield main.app

.. _http-client-mocking:

Mocking
-------

respx_ does not natively support HTTPX2 yet.
For the time being, you will have to add a development dependency on pytest-httpx2_ and use ``httpx2_mock`` instead of ``respx_mock``.

Unlike the standard ``respx_mock`` fixture, the ``httpx2_mock`` repoerts an error by default if any mock is declared but not called.
In cases where that is expected, you will need to add a mark to tell pytest-httpx2 that this is fine.

.. code-block:: python

   import pytest


   @pytest.mark.httpx2(assert_all_called=False)
   @pytest.mark.asyncio
   async def test_something() -> None: ...

pytest-httpx2 unfortunately does not declare this marker, so if you use this, you will also need to add the following block to your :file:`pyproject.toml`:

.. code-block:: toml

   [tool.pytest.ini_options]
   markers = [
       "httpx2: implemented by pytest-httpx2 but not registered correctly"
   ]

Mocks that return ``httpx.Response`` from ``return_value`` or ``side_effect`` of a respx mock must continue to use ``httpx.Response`` even though the rest of the application is using HTTPX2.
respx will not recognize ``httpx2.Response`` and will not handle the mock correctly if it is used.
