#####################
IVOA protocol support
#####################

The IVOA web protocols aren't entirely RESTful and have some unusual requirements that are not provided by modern web frameworks.
Safir provides some FastAPI support facilities to make implementing IVOA services easier.

Query parameter case insensitivity
==================================

Many IVOA protocols require the key of a query parameter to be case-insensitive.
For example, the requests ``GET /api/foo?param=bar`` and ``GET /api/foo?PARAM=bar`` are supposed to produce identical results.
Safir provides `safir.middleware.ivoa.CaseInsensitiveQueryMiddleware` to implement this protocol requirement.

Add this middleware to the FastAPI application:

.. code-block:: python

   from safir.middleware.ivoa import CaseInsensitiveQueryMiddleware

   app = FastAPI()
   app.add_middleware(CaseInsensitiveQueryMiddleware)

In the route handlers, declare all query parameters in all lowercase.
For instance, for the above example queries:

.. code-block:: python

   @app.get("/api/foo")
   async def get_foo(param: str) -> Response:
       result = do_something_with_param(param)

The keys of all incoming query parameters will be converted to lowercase by the middleware before the route handler is called.
The value will be unchanged; so, for example, with a request of ``GET /api/foo?PARAM=BAR``, the value of ``param`` will still be ``BAR``, not ``bar``.

The OpenAPI interface specification will only document the lowercase form of the parameters, but all other case combinations will be supported because the middleware will rewrite the incoming request.
