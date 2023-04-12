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

To do this, add a shutdown hook to your application:

.. code-block:: python

   from safir.dependencies.http_client import http_client_dependency

   app = FastAPI()


   @app.on_event("shutdown")
   async def shutdown_event() -> None:
       await http_client_dependency.aclose()

You can add this line to an existing shutdown hook if you already have one.

Using the httpx.AsyncClient
===========================

To use the client in a handler, just request it via a FastAPI dependency:

.. code-block:: python

   from safir.dependencies.http_client import http_client_dependency


   @routes.get("/")
   async def get_index(
       http_client: httpx.AsyncClient = Depends(http_client_dependency),
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

You can do this in a fixture to avoid code duplication.
