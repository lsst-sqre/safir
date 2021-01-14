####################################
Application and request storage keys
####################################

Safir apps use the key storage on the `aiohttp.web.Application` instance to globally store data.
Middleware also stores data in the `aiohttp.web.Request` instances.
This page describes the conventions and keys that Safir-based apps use.

Conventions
===========

Use the root app for storage
----------------------------

Safir apps typically have two `~aiohttp.web.Application` instances: a root application and a sub-application.
The sub-application serves externally-accessible routes under the application's name (``/<app-name>/``), while the root application serves internally-accessible routes relative to the root path (``/``).

**Safir attaches data to the root application whenever possible.**

In a request context, you can access application data, regardless of whether it is an internal or external route using the `aiohttp.web.Request.config_dict` lookup method:

.. code-block:: python

   @routes.get("/")
   async def get_index(request: web.Request) -> web.Response:
       """GET /<path>/ (the app's external root)."""
       metadata = request.config_dict["safir/metadata"]
       data = {"_metadata": metadata}
       return web.json_response(data)

safir/ key prefix
-----------------

Safir uses the ``safir/`` prefix for keys to prevent collisions with your code.
If your application adds custom data (outside the Safir framework) to the application, consider using a custom prefix to namespace that data.

Safir's application keys
========================

These keys are available from the root application in general, or from the `~aiohttp.web.Request.config_dict` attribute of `~aiohttp.web.Request` objects in handlers:

``safir/config``
    The conventional key for storing your application's configuration instance.

``safir/http_client``
    The `aiohttp.ClientSession` created by `safir.http.init_http_session` generator.
    See :doc:`./http-client`.

``safir/metadata``
    The application's metadata dictionary.

Safir's request keys
====================

These keys are available directly from `~aiohttp.web.Request` objects in handlers (without using ``config_dict``):

``safir/logger``
    This is a structlog logger added to the request by the logging middleware.
    See :doc:`./logging`.
