# Change log

All notable changes to Safir will be documented in this file.

Versioning follows [semver](https://semver.org/).

This project uses [scriv](https://scriv.readthedocs.io/en/stable/) to maintain the change log.
Changes for the upcoming release can be found in [changelog.d](https://github.com/lsst-sqre/safir/tree/main/changelog.d/).

<!-- scriv-insert-here -->

<a id='changelog-4.3.0'></a>
## 4.3.0 (2023-05-23)

### New features

- All `delete_*` APIs in the mock Kubernetes API now support `grace_period_seconds` and a `V1DeleteOptions` body. Both are ignored.
- `delete_namespaced_job` in the mock Kubernetes API now requires `propagation_policy` to be passed as a keyword argument if provided, and does not require it be set. It is validated against the values recognized by Kubernetes, and if set to `Orphan`, pods created by the job are not deleted.

### Bug fixes

- When reporting an error response to Slack using `SlackWebException`, put the response body in an attachment instead of a regular block, since it may be a full HTML error page. An attachment tells Slack to hide long content by default unless the viewer expands it.

<a id='changelog-4.2.2'></a>
## 4.2.2 (2023-05-17)

### Bug fixes

- Revert the documentation change in 4.2.1 to restore cross-references, since the docs-linkcheck failure appears to be a false positive.

### Other changes

- Safir now uses [scriv](https://scriv.readthedocs.io/en/latest/) to maintain its change log.

## 4.2.1 (2023-05-17)

### Bug fixes

- Fix syntax of literals in the `MockKubernetesApi` docstring.

## 4.2.0 (2023-05-17)

### New features

- Add create, delete, read, list (with watches), and (limited) patch support for `Ingress` objects to the mock Kubernetes API.
- Add create, delete, read, and list (with watches) support for `Job` objects to the mock Kuberntes API, and mock the `BatchV1Api`.
- Add delete, read, and list (with watches) support for `Service` objects to the mock Kubernetes API.
- Add support for label selectors to `list_namespaced_pod` in the mock Kubernetes API.
- Add `create_namespaced_persistent_volume_claim` to the mock Kubernetes API for testing.
- Add support for deleting custom resources to the mock Kubernetes API.

### Bug fixes

- `SlackWebException` now extracts the method and URL of the request from more httpx exceptions, and avoids exceptions when the request information is not present.

## 4.1.0 (2023-05-08)

### New features

- Add `read_*` methods for `ConfigMap` and `ResourceQuota` to the mock Kubernetes API for testing.
- Add `patch_namespaced_pod_status` to the mock Kubernetes API for testing. Application code is unlikely to call this, but it's useful for test suites.
- The mock `list_namespaced_pod` Kubernetes API now supports watches (but be aware that all changes must be made through the API).

### Bug fixes

- Fix concurrency locking when watching namespace events in the Kubernetes testing mock. The previous logic degenerated into busy-waiting rather than correctly waiting on a condition variable.
- Watches for namespace events using the mock Kubernetes API now start with the next event, not the first stored event, if `resource_version` is not set, aligning behavior with the Kubernetes API.

## 4.0.0 (2023-04-19)

### Backwards-incompatible changes

- Safir now requires a minimum Python version of 3.11.
- `safir.pydantic.validate_exactly_one_of` is now a Pydantic root validator instead of an individual field validator, which simplifies how it should be called.
- Custom Kubernetes objects are no longer copied before being stored in the Kubernetes mock by `create_namespaced_custom_object`, and no longer automatically get a `metadata.uid` value. This brings handling of custom objects in line with the behavior of other mocked `create_*` and `replace_*` APIs.
- All objects stored in the Kubernetes mock will be modified to set `api_version`, `kind`, and (where appropriate) `namespace`. If any of those values are set in the object, they are checked for correctness and rejected with `AssertionError` if they don't match the API call and its parameters.
- The mocked `create_*` Kubernetes APIs now use the name `body` for the parameter containing the API object, instead of using some other name specific to the kind of object. This fixes compatibility with the Python Kubernetes API that this class is mocking.

### New features

- The new `safir.redis.PydanticRedisStorage` class enables you to store Pydantic model objects in Redis.
  A `safir.redis.EncryptedPydanticRedisStorage` class also encrypts data in Redis.
  To use the `safir.redis` module, install Safir with the `redis` extra (i.e., `pip install safir[redis]`).
- Add `safir.fastapi.ClientRequestError` base class for exceptions and the corresponding exception handler `safir.fastapi.client_request_error_handler`. These may be used together to raise structured exceptions and automatically transform them into structured HTTP errors with the correct HTTP status code and an error body compatible with `safir.models.ErrorModel` and FastAPI's own internally-generated errors.
- Add `safir.slack.webhook.SlackWebException`, which is a child class of `safir.slack.webhook.SlackException` that knows how to capture and report details from an underlying HTTPX exception.
- Add a `safir.testing.kubernetes.strip_none` helper function that makes it easier to compare Kubernetes objects against expected test data.
- Add a `get_namespace_objects_for_test` method to the Kubernetes mock to retrieve all objects (of any kind) in a namespace.
- Add a mock for the `list_nodes` Kubernetes API, which returns data set by a call to the new `set_nodes_for_test` method.
- Add optional rudimentary namespace tracking to the Kubernetes mock. Namespaces can be created, deleted (which deletes all objects in the namespace), read, and listed. Explicit namespace creation remains optional; if an object is created in a namespace and that namespace does not exist, one will be implicitly created by the mock.
- Add support for namespaced events (the older core API, not the new events API) to the Kubernetes mock. Newly-created pods with the default initial status post an event by default; otherwise, events must be created by calling the mocked `create_namespaced_event` API. The `list_namespaced_event` API supports watches with timeouts.
- Add rudimentary support for `NetworkPolicy`, `ResourceQuota`, and `Service` objects to the Kubernetes mock.
- Add a `safir.github` module for writing GitHub integrations with GidgetHub and Pydantic modeling. `safir.github.GitHubAppClientFactory` helps create authenticated clients for GitHub Apps and app installations. `safir.github.models` contains Pydantic models for GitHub v3 REST API resources. `safir.github.webhooks` contains Pydantic models for GitHub webhook payloads.

### Bug fixes

- Stop adding the `X-Auth-Request-User` header to the OpenAPI schema for routes that use `auth_dependency` or `auth_logger_dependency`.

### Other changes

- The `safir.testing.kubernetes.MockKubernetesApi` mock now has rudimentary API documentation for the Kubernetes APIs that it supports.
- The documentation for running commands with `tox` has been updated for the new command-line syntax in tox v4.

## 3.8.0 (2023-03-15)

### New features

- Add `safir.slack.webhook.SlackWebhookClient` and accompanying models to post a structured message to Slack via an incoming webhook. Add a `safir.slack.blockkit.SlackException` base class that can be used to create exceptions with supplemental metadata that can be sent to Slack as a formatted alert.
- Add a FastAPI route class (`safir.slack.webhook.SlackRouteErrorHandler`) that reports all uncaught exceptions to Slack using an incoming webhook.
- Add `safir.datetime.format_datetime_for_logging` to convert a `datetime` object into an easily human-readable representation.
- Add `safir.testing.slack.mock_slack_webhook` and an associated mock class to mock a Slack webhook for testing.
- Add `microseconds=True` parameter to `safir.datetime.current_datetime` to get a `datetime` object with microseconds filled in. By default, `current_datetime` suppresses the microseconds since databases often cannot store them, but there are some timestamp uses, such as error reporting, that benefit from microseconds and are never stored in databases.

## 3.7.0 (2023-03-06)

### New features

- Add a `safir.testing.uvicorn.spawn_uvicorn` helper function to spawn an ASGI app under an external Uvicorn process. Normally, ASGI apps should be tested by passing the app directly to an `httpx.AsyncClient`, but in some cases (such as Selenium testing) the app needs to listen to regular HTTP requests.
- `safir.database.initialize_database` now creates a non-default schema if the underlying SQLAlchemy model declares one.

### Bug fixes

- After `safir.logging.configure_uvicorn_logging` was called, exception tracebacks were no longer expanded. Add the missing processor to the logging stack.
- In `safir.logging.configure_uvicorn_logging`, send the access log to standard output instead of combining it with all other messages on standard error.

## 3.6.0 (2023-02-03)

### New features

- Add a `safir.models.ErrorLocation` enum holding valid values for the first element of the `loc` array in `safir.models.ErrorModel`. Due to limitations in Python typing, `loc` is not type-checked against this enum, but it may be useful to applications constructing FastAPI-compatible error messages.
- Add `safir.datetime.current_datetime` to get a normalized `datetime` object representing the current date and time.
- Add `safir.datetime.isodatetime` and `safir.datetime.parse_isodatetime` to convert to and from the most useful form of ISO 8601 dates, used by both Kubernetes and the IVOA UWS standard. Also add `safir.pydantic.normalize_isodatetime` to accept only that same format as input to a Pydantic model with a `datetime` field.

## 3.5.0 (2023-01-12)

### New features

- Add new helper class `safir.gcs.SignedURLService` to generate signed URLs to Google Cloud Storage objects using workload identity. To use this class, depend on `safir[gcs]`.
- Add the `safir.testing.gcs` module, which can be used to mock the Google Cloud Storage API for testing. To use this module, depend on `safir[gcs]`.
- Add new helper class `safir.pydantic.CamelCaseModel`, which is identical to `pydantic.BaseModel` except with configuration added to accept camel-case keys using the `safir.pydantic.to_camel_case` alias generator and overrides of `dict` and `json` to export in camel-case by default.

## 3.4.0 (2022-11-29)

### New features

- `safir.logging.configure_logging` and `safir.logging.configure_uvicorn_logging` now accept `Profile` and `LogLevel` enums in addition to strings for the `profile` and `log_level` parameters. The new enums are preferred. Support for enums was added in preparation for changing the FastAPI template to use `pydantic.BaseSettings` for its `Configuration` class and validate the values of the `profile` and `log_level` configuration parameters.
- Add new function `safir.pydantic.normalize_datetime`, which can be used as a Pydantic validator for `datetime` fields. It also allows seconds since epoch as input, and ensures that the resulting `datetime` field in the model is timezone-aware and in UTC.
- Add new function `safir.pydantic.to_camel_case`, which can be used as a Pydantic alias generator when a model needs to accept attributes with camel-case names.
- Add new function `safir.pydantic.validate_exactly_one_of`, which can be used as a model validator to ensure that exactly one of a list of fields was set to a value other than `None`.

### Bug fixes

- In `safir.testing.kubernetes.patch_kubernetes`, correctly apply a spec to the mock of `kubernetes_asyncio.client.ApiClient`. Due to an ordering bug in previous versions, the spec was previously a mock object that didn't apply any constraints.

## 3.3.0 (2022-09-15)

### New features

- Add new function `safir.logging.configure_uvicorn_logging` that routes Uvicorn logging through structlog for consistent formatting. It also adds context to Uvicorn logs in the format recognized by Google's Cloud Logging.
- Support the newer project metadata structure and URL naming used by `pyproject.toml`-only packages in `safir.metadata.get_metadata`.

## 3.2.0 (2022-05-13)

### New features

- New support for [arq](https://arq-docs.helpmanual.io), the Redis-based asyncio distributed queue package. The `safir.arq` module provides an arq client and metadata/result data classes with a mock implementation for testing. The FastAPI dependency, `safir.dependencies.arq.arq_dependency`, provides a convenient way to use the arq client from HTTP handlers.

## 3.1.0 (2022-06-01)

### New features

- Add new FastAPI middleware `CaseInsensitiveQueryMiddleware` to aid in implementing the IVOA protocol requirement that the keys of query parameters be case-insensitive.

## 3.0.3 (2022-05-16)

### Bug fixes

- Correctly handle the possibility that `request.client` is `None`.

## 3.0.2 (2022-03-25)

### Bug fixes

- Fix handling of passwords containing special characters such as `@` and `/` in `safir.database`.

## 3.0.1 (2022-02-24)

### Bug fixes

- `safir.database` retains the port in the database URL, if provided.

## 3.0.0 (2022-02-23)

### Backward-incompatible changes

- `XForwardedMiddleware` no longer sets `forwarded_proto` in the request state and instead directly updates the request scope so that subsequent handlers and middleware believe the request scheme is that given by an `X-Forwarded-Proto` header. This fixes the scheme returned by other request methods and attributes such as `url_for` in cases where the service is behind an ingress that terminates TLS.

### New features

- Add new FastAPI dependencies `auth_dependency` and `auth_logger_dependency` from the `safir.dependencies.gafaelfawr` module. `auth_dependency` returns the username of the user authenticated via Gafaelfawr (pulled from the `X-Auth-Request-User` header. `auth_logger_dependency` returns the same logger as `logger_dependency` but with the `user` parameter bound to the username from `auth_dependency`.
- Add utility functions to initialize a database and create a sync or async session. The session creation functions optionally support a health check to ensure the database schema has been initialized.
- Add new FastAPI dependency `db_session_dependency` that creates a task-local async SQLAlchemy session.
- Add utility functions `datetime_from_db` and `datetime_to_db` to convert between timezone-naive UTC datetimes stored in a database and timezone-aware UTC datetimes used elsewhere in a program.
- Add a `run_with_async` decorator that runs the decorated async function synchronously. This is primarily useful for decorating Click command functions (for a command-line interface) that need to make async calls.

## 2.4.2 (2022-01-24)

### New features

- Add a very basic and limited implementation of `list_namespaced_pod` to `safir.testing.kubernetes`.

## 2.4.1 (2022-01-14)

### Bug fixes

- In the Kubernetes mock API, change the expected body for `patch_namespaced_custom_object_status` to reflect the need to send a JSON patch for the entirety of the `/status` path in order to work around a kubernetes_asyncio bug.

## 2.4.0 (2022-01-13)

### New features

- Add an `initialize_kubernetes` helper function to load Kubernetes configuration. Add the `safir.testing.kubernetes` module, which can be used to mock the Kubernetes API for testing. To use the new Kubernetes support, depend on `safir[kubernetes]`.

## 2.3.0 (2021-12-13)

### New features

- When logging in JSON format, use `severity` instead of `level` for the log level for compatibility with Google Log Explorer.
- In the FastAPI `logger_dependency`, add log information about the incoming requst in a format compatible with Google Log Explorer.

## 2.2.0 (2021-11-09)

### Bug fixes

- Restore previous `http_client_dependency` behavior by enabling following redirects by default. This adjusts for the change of defaults in HTTPX 0.20.0.

## 2.1.1 (2021-10-29)

### Other changes

- Require structlog 21.2.0 and adjust logger configuration of exception handling for the expectations of that version.

## 2.1.0 (2021-08-09)

### New features

- Add `safir.models.ErrorModel`, which is a model of the error message format preferred by FastAPI. Using the model is not necessary but it's helpful to reference it in API documentation to generate more complete information about the error messages.

### Bug fixes

- Mark all FastAPI dependencies as async so that FastAPI doesn't run them in an external thread pool.

## 2.0.1 (2021-06-24)

### New features

- Defer creation of `httpx.AsyncClient` until the first time it is requested. Allow re-creation after `aclose()`, which makes it easier to write test suites.

## 2.0.0 (2021-06-21)

### Backward-incompatible changes

As of this release, Safir is a helper library for FastAPI applications instead of aiohttp applications. Much of the library has changed. Authors of software that uses Safir should read the documentation again as part of the upgrade to FastAPI.

Included in this release is:

- A FastAPI dependency to provide a structlog logger as configured by the `safir.logging` package, replacing the aiohttp middleware.
- A FastAPI dependency to provide a global `httpx.AsyncClient`, replacing the middleware that provided an aiohttp client.
- Starlette (FastAPI) middleware to parse `X-Forwarded-*` headers and update request information accordingly.
- `safir.metadata.get_metadata` now returns a [Pydantic](https://docs.pydantic.dev/) model.

As of this release, Safir only supports Python 3.8 or later.

## 1.0.0 (2021-06-18)

Safir v1 will be the major release supporting aiohttp. Starting with Safir v2, Safir will become a support library for [FastAPI](https://fastapi.tiangolo.com/) applications.

This release has no significant difference from 0.2.0. The version bump is to indicate that the aiohttp support is stable.

## 0.2.0 (2021-06-10)

### New features

- `configure_logging` now supports an optional `add_timestamp` parameter (false by default) that adds a timestamp to each log message.

## 0.1.1 (2021-01-14)

### Bug fixes

- Fix duplicated log output when logging is configured multiple times.

## 0.1.0 (2020-02-26)

### New features

- The first release of Safir featuring:

  - `safir.http` for adding an `aiohttp.ClientSession` to your application.
  - `safir.logging` for configuring structlog loggers.
  - `safir.metadata` helps your gather and structure metadata about your application for publishing on metadata endpoints.
  - `safir.middleware` includes a logging middleware that adds a logger with bound context about the request to your Request object.
  - Documentation about these features and a tutorial for starting a new application with the `roundtable_aiohttp_bot` template.
