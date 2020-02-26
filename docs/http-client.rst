########################
Using the aiohttp client
########################

Safir helps you manage a single `aiohttp.ClientSession` for your application.
Using a single HTTP client improves performance by reusing connections.

Setting up the aiohttp.ClientSession
====================================

To initialize the client, add `safir.http.init_http_session` as a cleanup context to your root application:

.. code-block:: python

   def create_app() -> web.Application:
       root_app = web.Application()
       root_app.cleanup_ctx.append(init_http_session)

       return root_app

The cleanup context ensures that the client session is closed when the application shuts down.

Using the ClientSession
=======================

`~safir.http.init_http_session` attaches the session to the ``safir/http_session`` key of the application.

Accessing the session directly from the app:

.. code-block:: python

   http_session = app["safir/http_session"]
   response = await http_session.get("https://keeper.lsst.codes")

Inside a request handler, use `~aiohttp.web.Request.config_dict`:

.. code-block:: python

   @routes.get("/")
   async def get_index(request: web.Request) -> web.Response:
       http_session = request.config_dict["safir/http_session"]
       response = await http_session.get("https://keeper.lsst.codes")
       data = await response.json()
       return web.json_response(data)
