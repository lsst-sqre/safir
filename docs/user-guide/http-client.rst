######################
Using the HTTPX client
######################

Safir helps you manage a single ``httpx.AsyncClient`` for your application.
Using a single HTTPX_ client improves performance by reusing connections.

Setting up the httpx.AsyncClient
================================

The ``httpx.AsyncClient`` will be dyanmically created during application startup.
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

Using the httpx.AsyncClient
===========================

To use the client in a handler, just request it via a FastAPI dependency:

.. code-block:: python

   from typing import Annotated

   from httpx import AsyncClient
   from safir.dependencies.http_client import http_client_dependency


   @routes.get("/")
   async def get_index(
       http_client: Annotated[AsyncClient, Depends(http_client_dependency)],
   ) -> Dict[str, Any]:
       response = await http_client.get("https://keeper.lsst.codes")
       return await response.json()

Testing considerations
======================

If you are using ``httpx.AsyncClient`` in your application tests as well, note that it will not trigger shutdown events, so if you trigger handlers that use the HTTP client, you will get a warning about an unclosed ``httpx.AsyncClient`` in your test output.
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
