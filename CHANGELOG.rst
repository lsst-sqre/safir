##########
Change log
##########

.. Headline template:
   X.Y.Z (YYYY-MM-DD)

2.4.1 (2022-01-14)
==================

- In the Kubernetes mock API, change the expected body for ``patch_namespaced_custom_object_status`` to reflect the need to send a JSON patch for the entirety of the ``/status`` path in order to work around a kubernetes_asyncio bug.

2.4.0 (2022-01-13)
==================

- Add an ``initialize_kubernetes`` helper function to load Kubernetes configuration.
  Add the ``safir.testing.kubernetes`` module, which can be used to mock the Kubernetes API for testing.
  To use the new Kubernetes support, depend on ``safir[kubernetes]``.

2.3.0 (2021-12-13)
==================

- When logging in JSON format, use ``severity`` instead of ``level`` for the log level for compatibility with Google Log Explorer.
- In the FastAPI ``logger_dependency``, add log information about the incoming requst in a format compatible with Google Log Explorer.

2.2.0 (2021-11-09)
==================

- Restore previous ``http_client_dependency`` behavior by enabling following redirects by default.
  This adjusts for the change of defaults in httpx 0.20.0.

2.1.1 (2021-10-29)
==================

- Require structlog 21.2.0 and adjust logger configuration of exception handling for the expectations of that version.

2.1.0 (2021-08-09)
==================

- Add ``safir.models.ErrorModel``, which is a model of the error message format preferred by FastAPI.
  Using the model is not necessary but it's helpful to reference it in API documentation to generate more complete information about the error messages.
- Mark all FastAPI dependencies as async so that FastAPI doesn't run them in an external thread pool.

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
