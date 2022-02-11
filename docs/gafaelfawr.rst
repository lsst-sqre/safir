###################################
Requiring Gafaelfawr authentication
###################################

Safir provides two FastAPI dependencies intended for applications designed to run behind a Kubernetes ingress configured to authenticate requests with `Gafaelfawr`_.

Getting the authenticated user
==============================

Gafaelfawr sets the ``X-Auth-Request-User`` HTTP header to the username of the user authenticated with a Gafaelfawr token.
To get that username, use the `~safir.dependencies.gafaelfawr.auth_dependency` FastAPI dependency, as follows:

.. code-block:: python

   from fastapi import Depends

   from safir.dependencies.gafaelfawr import auth_dependency


   @app.get("/route")
   async def get_rounte(user: str = Depends(auth_dependench)) -> Dict[str, str]:
       # Route implementation using user.
       return {"some": "data"}

If the request does not have the Gafaelfawr header set, it will be rejected by FastAPI with a 422 status code.

To safely use this dependency, the application must be configured so that all requests will go through an ingress configured to use Gafaelfawr.
If this is not the case (if, for example, the application is directly exposed to the Internet), the person sending the request could include the header that would be set by Gafaelfawr and assert any identity that they chose, which is obviously insecure.

Including the authenticated user in logging
===========================================

To include the authenticated user in log messages from a handler, use the `~safir.dependencies.gafaelfawr.auth_logger_dependency` dependency instead of the `~safir.dependencies.logger.logger_dependency`.
It works the same way, but additionally binds the ``user`` context variable to the authenticated user, obtained via `~safir.dependencies.gafaelfawr.auth_dependency`.

For more details, see :ref:`logging-in-handlers`.
