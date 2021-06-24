##########
Change log
##########

.. Headline template:
   X.Y.Z (YYYY-MM-DD)

2.0.1 (2021-06-24)
==================

- Defer creation of ``httpx.AsyncClient`` until the first time it is requested.
  Allow re-creation after ``aclose()``, which makes it easier to write test suites.

2.0.0 (2021-06-21)
==================

As of this release, Safir is a helper library for FastAPI applications instead of aiohttp applications.
Much of the library has changed.
Authors of software that uses Safir should read the documentation again as part of the upgrade to FastAPI.

Included in this release is:

- A FastAPI dependency to provide a structlog logger as configured by the ``safir.logging`` package, replacing the aiohttp middleware.
- A FastAPI dependency to provide a global ``httpx.AsyncClient``, replacing the middleware that provided an aiohttp client.
- Starlette (FastAPI) middleware to parse ``X-Forwarded-*`` headers and update request information accordingly.
- ``safir.metadata.get_metadata`` now returns a Pydantic_ model.

.. _Pydantic: https://pydantic-docs.helpmanual.io/

As of this release, Safir only supports Python 3.8 or later.

1.0.0 (2021-06-18)
==================

Safir v1 will be the major release supporting aiohttp.
Starting with Safir v2, Safir will become a support library for FastAPI_ applications.

.. _FastAPI: https://fastapi.tiangolo.com/

This release has no significant difference from 0.2.0.
The version bump is to indicate that the aiohttp support is stable.

0.2.0 (2021-06-10)
==================

- ``configure_logging`` now supports an optional ``add_timestamp`` parameter (false by default) that adds a timestamp to each log message.
- Update dependencies.

0.1.1 (2021-01-14)
==================

- Fix duplicated log output when logging is configured multiple times.
- Update dependencies.

0.1.0 (2020-02-26)
==================

- The first release of Safir featuring:
  
  - ``safir.http`` for adding an ``aiohttp.ClientSession`` to your application.
  - ``safir.logging`` for configuring structlog loggers.
  - ``safir.metadata`` helps your gather and structure metadata about your application for publishing on metadata endpoints.
  - ``safir.middleware`` includes a logging middleware that adds a logger with bound context about the request to your Request object.
  - Documentation about these features and a tutorial for starting a new application with the ``roundtable_aiohttp_bot`` template.
