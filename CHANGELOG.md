# Change log

All notable changes to Safir will be documented in this file.

Versioning follows [semver](https://semver.org/).

This project uses [scriv](https://scriv.readthedocs.io/en/stable/) to maintain the change log.
Changes for the upcoming release can be found in [changelog.d](https://github.com/lsst-sqre/safir/tree/main/changelog.d/).

<!-- scriv-insert-here -->

<a id='changelog-14.2.0'></a>
## 14.2.0 (2026-01-30)

### New features

- Add new `safir.testing.data.Data` class for managing test data. This class should be created in a pytest fixture and provides methods to read test data in various formats and check test results against expected output, optionally updating the expected output.

<a id='changelog-14.1.3'></a>
## 14.1.3 (2026-01-21)

### Bug fixes

- Pin `aiokafka` because the latest release breaks `faststream`:
  https://github.com/aio-libs/aiokafka/issues/1147

<a id='changelog-14.1.2'></a>
## 14.1.2 (2025-12-02)

### Bug fixes

- app metrics - Don't raise exceptions when the Schema Manager goes down in the
middle of registering event publishers. If the Schema Manager went away in the
time between when an event publisher was successfully created and an attempt at
creating another event publisher, the app metrics error handling wrapper
incorrectly set the EventManager state to uninitialized, which made other parts
of the event manager throw EventManagerUninitializedErrors. This made it so
that applications using the app metrics functionality were broken until
restart.

- Correct spelling of `EventManagerUninitializedError`

<a id='changelog-14.1.1'></a>
## 14.1.1 (2025-11-14)

### Bug fixes

- Update FastStream pin for the `kafka` extra to 0.6, fixing an incompatibility with FastAPI 0.121.
- Use new wait strategy syntax for the test containers provided by Safir, fixing some deprecation warnings.

<a id='changelog-14.1.0'></a>
## 14.1.0 (2025-10-30)

### New features

- Add `safir.kafa.FastStreamErrorHandler`, a [FastStream ExceptionMiddleware](https://faststream.ag2.ai/latest/getting-started/middlewares/exception/) to report uncaught errors to external services.

### Other changes

- Ignore https://arq-docs.helpmanual.io links in link check, they frequently time out when checked from GitHub actions.
- Safir is now tested with Python 3.14 as well as 3.12 and 3.13.

<a id='changelog-14.0.0'></a>
## 14.0.0 (2025-09-30)

### Backwards-incompatible changes

- `safir.slack.SlackWebhookClient.post_uncaught_exception` has been removed. `safir.slack.SlackWebhookClient.post_exception` now handles non-`SlackException` exceptions.

  To make your app compatible, change all `post_uncaught_exception` calls to `post_exception`. The behavior will be the same, except the message will start with "Error in..." instead of "Uncaught exception in..."

### New features

- `safir.sentry.report_exception` will notify Slack and/or Sentry if either integration is configured
- UWS `TaskError` Sentry instrumentation now contains info about the original exception
- The UWS helpers now notify both Slack and Sentry about errors

<a id='changelog-13.0.1'></a>
## 13.0.1 (2025-09-23)

### Bug fixes

- `safir.sentry.initialize_sentry` now has the correct (though unfortunate) type of `Any` for `**additional_kwargs`

### Other changes

- Starlette deprecated the `HTTP_422_UNPROCESSABLE_ENTITY` constant and
  changed it to `HTTP_422_UNPROCESSABLE_CONTENT` in [this
  PR](https://github.com/Kludex/starlette/pull/2939). We could either
  change this constant in our code, or just use the status code int
  directly.

  Use status code directly here rather than the new constant in
  to avoid having to increase the lower bound on starlette. This is the
  choice that the FastAPI folks made in [this
  PR](https://github.com/fastapi/fastapi/pull/14077/files).

<a id='changelog-13.0.0'></a>
## 13.0.0 (2025-09-16)

### Backwards-incompatible changes

- `safir.SentryException` and `safir.SentryWebException` are gone. The functionality to send Sentry metadata from custom exceptions has been moved into `safir.slack.blockkit.SlackException`.

  To convert existing subclasse of `SentryException` and `SentryWebException`:

  1. Inherit from `SlackException` or `SlackWebException` instead
  1. Move any logic that sets tags, contexts or attachments into a `to_sentry` method that returns a `safir.slack.sentry.SentryEventInfo` object.

- Move Kafka dependencies to an extra. Users of safir.kafka or safir.metrics must now depend on `safir[kafka]`.

### New features

- Add Sentry initialization helpers that get config values from environment variables and enhance reporting of `SentryException`s.

### Bug fixes

- Catch import errors in Safir modules that depend on extra dependencies and report a custom error indicating which extra dependency is required.

<a id='changelog-12.1.2'></a>
## 12.1.2 (2025-08-28)

### Bug fixes

- `start_time` in pod.status now stored as datetime.datetime and serialized in `next_event()`

<a id='changelog-12.1.1'></a>
## 12.1.1 (2025-08-28)

### Bug fixes

- Correct K8s pod status.start_time format.

<a id='changelog-12.1.0'></a>
## 12.1.0 (2025-08-28)

### New features

- Added start_time to status in Kubernetes mock for pod.

<a id='changelog-12.0.1'></a>
## 12.0.1 (2025-08-25)

### Bug fixes

- Add lower version bounds on the google-auth and google-cloud-storage dependencies so that dependency resolvers will not downgrade them to ancient versions in order to upgrade cachetools.

<a id='changelog-12.0.0'></a>
## 12.0.0 (2025-08-07)

### Backwards-incompatible changes

- Move arq metrics helpers out of `safir.metrics`, to the separately importable `safir.metrics.arq`. This avoids the `safir` package depending on the `arq` package, which is only installed with the `safir[arq]` extra.

### New features

- App metrics Avro schemas are now registered with a compatibility type of "NONE". Any event model changes will be now allowed and no compatibility errors will ever be thrown during initialization.

<a id='changelog-11.3.1'></a>
## 11.3.1 (2025-08-05)

### Bug fixes

- metrics: calculate arq time-in-queue value with millisecond precision. This prevents inaccurate and negative values.

<a id='changelog-11.3.0'></a>
## 11.3.0 (2025-08-04)

### New features

#### Generic Arq metrics

You can now instrument your [arq](https://github.com/python-arq/arq) jobs to emit an `arq_job_run` app metric with a `queue` tag and a `time_in_queue` field. You can use this to help you decide if and when you need to add more workers.

To enable this, you need to:

* Add app metrics configuration to your app
* Add `queue` to the list of fields in the Sasquatch app metrics configuration
* Create a `safir.metrics.EventManager` and pass it to `safir.metrics.initialize_arq_metrics` in your `WorkerSettings.on_startup` function.
* Generate an `on_job_start` function by passing a queue name to `safir.metrics.make_on_job_start`.
  Make sure you shut this event manager down cleanly in your shutdown function.

- Add a function to publish metrics for arq queues. Your app is expected to call this function periodically somehow, probably with a Kubernetes CronJob.

<a id='changelog-11.2.0'></a>
## 11.2.0 (2025-07-28)

### New features

#### App metrics application resiliency

If the underlying app metrics infrastructure is degraded, like if Kafka or the Schema Registry are not available, the Safir app metrics code now tries very hard to not crash or your instrumented application.

Instead of of raising exceptions, it will log error-level messages and put itself into an error state. Once in this error state, it will not even try to interact with any underlying infrastructure, which means it will not even try to send metrics for a configurable amount of time.
It will instead only log error messages.

If this happens during initialization, you will have to restart your app after the underlying infrastructure is fixed to start sending metrics again. if This happens after successful initialization, the app may start sending metrics again by itself after the underlying infrastructure is fixed.

There are two new config options:

- The `raise_on_error` config option to `KafkaMetricsConfiguration` can be set to `False` to raise all exceptions to the instrumented app instead of swallowing them and logging errors.
- The `backoff_interval` config option to `KafkaMetricsConfiguration` sets the amount of time to wait before trying to send metrics again if an error state is entered after initialization.

### Bug fixes

- Adjust `SchemaRegistryContainer` to work with the latest release of testcontainers. This may result in the wrong Confluent Schema Registry `host_name` setting if non-standard connection modes are used with that container.
- Close FastStream brokers with `stop` instead of `close` and require FastStream 0.5.44 or later to avoid deprecation warnings.

<a id='changelog-11.1.0'></a>
## 11.1.0 (2025-07-10)

### New features

- `GitHubPullRequestModel` now contains a `head` value, which is a model that contains a `sha` value. This is the latest commit SHA on the head branch of the PR in a `GitHubPullRequestEventModel`.

<a id='changelog-11.0.0'></a>
## 11.0.0 (2025-05-28)

### Backwards-incompatible changes

- Change the `manage_kafka` flag to `safir.metrics.KafkaEventManager` to `manage_kafka_broker`. It now only controls whether the Kafka broker is started and stopped. The Kafka admin client is unconditionally managed (started and stopped) by `KafkaEventManager` and should not be shared with any other application use.

### New features

- Allow an application to pass an existing FastStream Kafka broker into `safir.metrics.BaseMetricsConfiguration.make_manager`. This simplifies metrics integration for Kafka applications with existing brokers, without requiring manual manager construction and losing the auto-selection of the no-op and mock event managers.
- Support the standard Pydantic `exclude_unset`, `exclude_defaults`, and `exclude_none` arguments to `PydanticRedisStorage.store`.
- Add `safir.testing.containers.FullKafkaContainer` and `safir.testing.containers.SchemaRegistryContainer` classes based on Testcontainers that create containers for Kafka and the Confluent schema registry, respectively. These classes are intended for use in fixtures or test configuration to enable testing against a local temporary Kafka cluster.
- Add `safir.testing.logging.parse_log_tuples` utility function to aid in testing structured log messages from applications using the Safir logging framework.

### Other changes

- `safir.testing` is now an implicit namespace package similar to `safir` so that safir-logging can provide a testing module. This should hopefully not cause any user-observable changes.

<a id='changelog-10.2.0'></a>
## 10.2.0 (2025-05-05)

### New features

- Add additional parameters `max_overflow`, `pool_size`, and `pool_timeout` to `safir.database.create_database_engine`. These are passed to the SQLAlchemy `create_async_engine` function and can be used to tweak pool behavior.
- Add additional parameters `connect_args`, `max_overflow`, `pool_size`, and `pool_timeout` to the `initialize` method of the database session FastAPI dependency. These parameters are passed to `create_database_engine` when creating the underlying engine.

<a id='changelog-10.1.0'></a>
## 10.1.0 (2025-04-23)

### New features

- `create_async_engine` now rewrites URLs with a scheme of `mysql` to use `mysql+asyncmy`, similar to the existing rewrite of `postgresql` to `postgresql+asyncpg`.
- Add an optional `connect_args` parameter to `create_async_engine` that can be used to pass parameters directly to the underlying database driver. This may be used to, for example, configure TLS settings.
- Add create, delete, read, and list (with watches) support for `PersistentVolume` objects to the mock Kubernetes API. These are not integrated with `PersistentVolumeClaim` objects; the user of the mock must create them separately.

<a id='changelog-10.0.0'></a>
## 10.0.0 (2025-02-24)

### Backwards-incompatible changes

- Safir now requires a minimum Python version of 3.12.

### New features

- Add `number` field to `GitHubCheckRunPrInfoModel` to capture the pull request number in GitHub check events.

<a id='changelog-9.3.0'></a>
## 9.3.0 (2025-02-11)

### New features

- Add new `register_create_hook_for_test` method on the mock Kubernetes API that allows the caller to register a callback that is called whenever an object of a given kind is created.
- Add create, delete, read, and list (with watches) support for `ServiceAccount` objects to the mock Kubernetes API.

### Bug fixes

- Declare Safir functions returning async generators with a return type of `AsyncGenerator`, not `AsyncIterator`. In most situations this does not matter, but `AsyncGenerator` has additional methods (such as `aclose`) that `AsyncIterator` does not have and is therefore more correct.

<a id='changelog-9.2.0'></a>
## 9.2.0 (2025-01-22)

### New features

- Add a new `safir.sentry` module that provides helper functions and custom exception types for improved Sentry integration.
- Allow the encryption key to be passed to `safir.redis.EncryptedPydanticRedisStorage` as a `pydantic.SecretStr` instead of `str`. This allows easier integration with secrets that come from Pydantic-parsed settings.

<a id='changelog-9.1.1'></a>
## 9.1.1 (2024-12-18)

### Bug fixes

- Unset the `ssl.VERIFY_X509_STRICT` flag in SSL contexts used for Kafka connections. Python 3.13 enables this flag by default, and the current certs that Strimzi generates for these Kafka endpoints are missing an Authority Key Identifier, which prevents connections when the flag is set.

<a id='changelog-9.1.0'></a>
## 9.1.0 (2024-12-17)

### New features

- Add new `CountedPaginatedQueryRunner` and a returned `CountedPaginatedList` model for services that want paginated database queries that always do a second query for the total count of records without pagination.

### Other changes

- Safir is now tested with Python 3.13 as well as Python 3.12.

<a id='changelog-9.0.1'></a>
## 9.0.1 (2024-12-11)

### Bug fixes

- Fix dependencies on safir-logging and safir-arq from the safir PyPI module to allow the latest versions to be installed.

<a id='changelog-9.0.0'></a>
## 9.0.0 (2024-12-11)

### Backwards-incompatible changes

- Rewrite the Safir UWS support to use Pydantic models for job parameters. Services built on the Safir UWS library will need to change all job creation dependencies to return Pydantic models.
- UWS clients must now pass an additional `job_summary_type` argument to `UWSAppSettings.build_uws_config` and implement `to_xml_model` in their implementation of `ParametersModel`, returning a subclass of the vo-models `Parameters` class.
- Use the Wobbly service rather than a direct database connection to store UWS job information. Services built on the Safir UWS library must now configure a Wobbly URL and will switch to Wobbly's storage instead of their own when updated to this release of Safir.
- Case-insensitivity of form `POST` parameters to UWS routes is now handled by middleware, and the `uws_post_params_dependency` function has been removed. Input parameter dependencies for UWS applications can now assume that all parameter keys will be in lowercase.
- Support an execution duration of 0 in the Safir UWS library, mapping it to no limit on the execution duration. Note that this will not be allowed by the default configuration and must be explicitly allowed by an execution duration validation hook.
- Convert all models returned by the Safir UWS library to Pydantic. Services built on the Safir UWS library will have to change the types of validator functions for destruction time and execution duration.
- Safir no longer provides the `safir.uws.ErrorCode` enum or the exception `safir.uws.MultiValuedParameterError`. These values were specific to a SODA service, and different IVOA UWS services use different error codes. The Safir UWS library now takes error code as a string, and each application should define its own set of error codes in accordance with the IVOA standard it is implementing.

### New features

- Add unit testing support for application metrics. Tests can define a mock application metrics event handler and inspect it after running application code to see what events would have been published.

### Bug fixes

- Append a colon after the error code when reporting UWS errors.

### Other changes

- Render all UWS XML output except for error VOTables using vo-models rather than hand-written XML templates.

<a id='changelog-8.0.0'></a>
## 8.0.0 (2024-11-26)

### Backwards-incompatible changes

- Add serializers to `HumanTimedelta` and `SecondsTimedelta` that serialize those Pydantic fields to a float number of seconds instead of ISO 8601 durations. This means those data types now can be round-tripped (serialized and then deserialized to the original value), whereas before they could not be.
- `parse_isodatetime` and `normalize_isodatetime` now accept exactly the date formats accepted by the IVOA DALI standard. This means seconds are now required, the trailing `Z` is now optional (times are always interpreted as UTC regardless), and the time is optional and interpreted as 00:00:00 if missing.

### New features

- Add new `safir.pydantic.UtcDatetime` type that is equivalent to `datetime` but coerces all incoming times to timezone-aware UTC. This type should be used instead of using `normalize_datetime` as a validator.
- Add new `safir.pydantic.IvoaIsoDatetime` type that accepts any ISO 8601 date and time that matches the IVOA DALI standard for timestamps. This follows the same rules as `parse_isodatetime` now follows. This type should be used instead of using `normalize_isodatetime` as a validator.
- Add new `safir.database.PaginatedLinkData` model that parses the contents of an HTTP `Link` header and extracts pagination information.
- Add `safir.database.drop_database` utility function to drop all database tables mentioned in a SQLAlchemy ORM schema and delete the Alembic version information if it is present. This is primarily useful for tests.
- Publishing a metrics event no longer waits on confirmation of message delivery to Kafka. This makes publishing much more performant. All events will still be delivered as long as an app awaits `EventManager.aclose` in its lifecycle.
- `safir.kafka.PydanticSchemaManager` takes an optional structlog `BoundLogger`. If not provided, the default logger is a `BoundLogger`, rather than a `logging.Logger`.
- Pass the `logger` parameter to `safir.metrics.KafkaMetricsConfiguration.make_manager` to the `PydanticSchemaManager` instance that it creates.
- Add `CaseInsensitiveFormMiddleware` to lower-case the keys of form `POST` parameters. This can be used to support the case-insensitive keys requirement of IVOA standards.

### Bug fixes

- Correctly validate stringified floating-point numbers of seconds as inputs to the `SecondsTimedelta` type instead of truncating it to an integer.
- Allow `timedelta` as a member of a union field in a `safir.metrics.EventPayload`.
- Add missing dependency on alembic to the `safir[uws]` extra.

### Other changes

- Document how to test an application's database schema against its Alembic migrations to ensure that the schema hasn't been modified without adding a corresponding migration.

<a id='changelog-7.0.0'></a>
## 7.0.0 (2024-11-08)

### Backwards-incompatible changes

- Remove `EventDuration` from `safir.metrics`. Instead, use Python's built-in `timedelta` as the type for any field that previously used `EventDuration`. It will be serialized the same way, as an Avro `double` number of seconds.

### Bug fixes

- Support multi-valued parameters as input to UWS `POST` routes when the values are specified by repeating the parameter.
- Declare that the `safir.metrics` package is typed by adding a `py.typed` file.

<a id='changelog-6.5.1'></a>
## 6.5.1 (2024-10-21)

### Bug fixes

- Allow and ignore extra attributes to `MetricsConfiguration` when metrics are disabled. This allows passing a partial metrics configuration even when they are disabled, which simplifies the structure of Phalanx configurations based on dumping the Helm values into a YAML configuraiton file.

<a id='changelog-6.5.0'></a>
## 6.5.0 (2024-10-18)

### New features

- Add new `safir.kafka` module to simplify configuring and constructing Kafka clients. Included in this module is `safir.kafka.PydanticSchemaManager`, which supports registering and evolving Avro schemas in the Confluent schema registry via Pydantic models. Based on @jonathansick's [kafkit](https://kafkit.lsst.io/) work.
- Add new `safir.metrics` module to enable publishing app metrics events.

### Bug fixes

- Fix integration issues with [vo-models](https://github.com/spacetelescope/vo-models) in the UWS support.

<a id='changelog-6.4.0'></a>
## 6.4.0 (2024-09-16)

### New features

- Add support functions for using Alembic to manage database schema migrations and to verify that the current database schema matches the expectations of the running application. The support in Safir is designed to use asyncpg for all database operations, which avoids having to add a separate dependency on a sync database client.
- Add Alembic schema management support to the UWS library. This support is likely temporary and will probably be replaced in the future with a standalone UWS database service.

<a id='changelog-6.3.0'></a>
## 6.3.0 (2024-08-20)

### New features

- `safir.logging` is now available as a separate PyPI package, `safir-logging`, so that it can be installed in environments where the full Safir dependency may be too heavy-weight or conflict with other packages. Packages that do depend on `safir` can and should ignore this change and continue to assume depending on `safir` will be sufficient to provide `safir.logging`.
- Allow the database URL passed to `DatabaseSessionDependency.initialize` to be a Pydantic `Url`. This simplifies logic for applications that use `EnvAsyncPostgresDsn` or other Pydantic URL types for their configuration.
- Allow the hook URL argument to `safir.testing.slack.mock_slack_webhook` to be a Pydantic `SecretStr`.

### Bug fixes

- `safir.logging` previously exported a `logger_name` variable holding the logger name configured via `safir.logging.configure_logging`. This variable was never documented and was not intended for use outside of the library. It is no longer exported, has been renamed, and is now private to the library.
- Fix construction of an `Availability` object reporting problems with the UWS database layer to use the correct field names and data type for the model.

<a id='changelog-6.2.0'></a>
## 6.2.0 (2024-08-02)

### New features

- Add new `safir.uws` and `safir.arq.uws` modules that provide the framework of an IVOA Universal Worker Service implementation.
- Add new `safir.testing.uws` module that provides a mock UWS job runner for testing UWS applications.
- `safir.arq` is now available as a separate PyPI package, `safir-arq`, so that it can be installed in environments where the full Safir dependency may be too heavy-weight or conflict with other packages. The `safir[arq]` dependency will continue to work as before (by installing `safir-arq` behind the scenes).
- Add new `abort_job` method to instances of `safir.arq.ArqQueue`, which tells arq to abort a job that has been queued or in progress. To successfully abort a job that has already started, the arq worker must enable support for aborting jobs.
- Add new utility function `safir.arq.build_arq_redis_settings`, which constructs the `RedisSettings` object used to create an arq Redis queue from a Pydantic Redis DSN.
- Add new `safir.arq.WorkerSettings` class that models the acceptable parameters for an arq `WorkerSettings` object or class that Safir applications have needed.
- Add new `safir.pydantic.SecondsDatetime` and `safir.pydantic.HumanDatetime` types for use in Pydantic models. These behave the same as `datetime.timedelta` fields but use custom validation. Both support a stringified number of seconds as input, and the latter also supports the interval strings parsed by `safir.datetime.parse_timedelta`.
- Add new types `safir.pydantic.EnvAsyncPostgresDsn` and `safir.pydantic.EnvRedisDsn`, which validate PostgreSQL and Redis DSNs but rewrite them based on the environment variables set by tox-docker. Programs using these types for their configuration will therefore automatically honor tox-docker environment variables when running the test suite. `EnvAsyncPostgresDsn` also enforces that the scheme of the DSN is compatible with asyncpg and the Safir database support.
- Add the decorator `safir.database.retry_async_transaction`, which retries a function or method a configurable number of times if it raises a SQLAlchemy exception from the underlying database API. This is primarily intended to retry database operations aborted due to transaction isolation.
- `safir.database.create_database_engine` now accepts the database URL as a Pydantic `Url` as well as a `str`.
- Allow the Slack webhook URL argument to `SlackWebhookClient` and `SlackRouteErrorHandler` to be given as a Pydantic `SecretStr` instead of a `str`. This simplifies code in applications that get that value from a secret.

### Other changes

- Safir is now built with [nox](https://nox.thea.codes/en/stable/index.html) instead of [tox](https://tox.wiki/).

<a id='changelog-6.1.0'></a>
## 6.1.0 (2024-07-12)

### New features

- Add `pull_requests` to `GitHubCheckSuiteModel` to capture info about any pull requests associated with a GitHub check suite event.

<a id='changelog-6.0.0'></a>
## 6.0.0 (2024-06-10)

### Backwards-incompatible changes

- Drop `safir.database.create_sync_session`. This was only used by services that used Dramatiq for task management, since Dramatiq is sync-only. Services based on Safir should switch to arq and use only async database connections.
- Drop `DatabaseSessionDependency.override_engine`. This was used for Gafaelfawr to share a database engine across all tests for speed, but this technique breaks with current versions of pytest-asyncio and is no longer used or safe to use.

### New features

- Allow the database password to be passed to `create_database_engine` and `DatabaseSessionDependency.initialize` as a Pydantic `SecretStr`.
- Add new function `safir.datetime.parse_timedelta`, which parses a human-friendly syntax for specifying time durations into a Python `datetime.timedelta`.
- Add support for `gs` URLs to `safir.gcs.SignedURLService`.
- Support pickling of `SlackException` so that subclasses of it can be thrown by arq workers and unpickled correctly when retrieving results.

### Bug fixes

- Correctly honor the `default_queue_name` argument to `RedisArqQueue.initialize`.

<a id='changelog-5.2.2'></a>
## 5.2.2 (2024-03-15)

### Bug fixes

- Ensure that per-request database sessions provided by `db_session_dependency` are cleaned up even if the request aborts with an uncaught exception.

<a id='changelog-5.2.1'></a>
## 5.2.1 (2024-02-19)

### Bug fixes

- Fix the return type of `safir.datetime.parse_isodatetime` to not include `None` since the function never returns `None`.

<a id='changelog-5.2.0'></a>
## 5.2.0 (2024-01-19)

### New features

- Add a FastAPI dependency for retrieving a Gafaelfawr delegated token from the request headers: `safir.dependencies.gafaelfawr.auth_delegated_token_dependency`.

### Bug fixes

- Rewrite `CaseInsensitiveQueryMiddleware` and `XForwardedMiddleware` as pure ASGI middleware rather than using the Starlette `BaseHTTPMiddleware` class. The latter seems to be behind some poor error reporting of application exceptions, has caused problems in the past due to its complexity, and is not used internally by Starlette middleware.

<a id='changelog-5.1.0'></a>
## 5.1.0 (2023-12-07)

### New features

- Add support for label selectors in the `list_node` method of the Kubernetes mock.

<a id='changelog-5.0.0'></a>
## 5.0.0 (2023-12-05)

### Backwards-incompatible changes

- Safir now depends on Pydantic v2. Python code that uses any part of Safir related to Pydantic will also need to update to Pydantic v2, since the API is significantly different. See the [Pydantic migration guide](https://docs.pydantic.dev/latest/migration/) for more information.
- `safir.pydantic.validate_exactly_one_of` is now a Pydantic model validator. It must be called with `mode="after"`, since it operates in the model rather than on a raw dictionary.
- Remove the `GitHubAppClientFactory.create_app_client` method, which does not work with the Gidgethub API. Instead, the documentation shows how to create a JWT with the `GitHubAppClientFactory` and pass it with requests.
- `safir.github.GitHubAppClientFactory` now expects the application ID and installation ID (for `create_installation_client`) to be of type `int`, not `str`. This appears to match what GitHub's API returns, but not what Gidgethub expects. The ID is converted to a string when passing it to Gidgethub.

### New features

- Allow the `safir.logging.LogLevel` enum to be created from strings of any case, which will allow the logging level to be specified with any case for Safir applications that use Pydantic to validate the field.
- Add validated but ignored optional `propagation_policy` arguments to every delete method of the Kubernetes mock for better compatibility with the actual Kubernetes API. Previously, this argument was only accepted by `delete_namespaced_job`.
- All mock Kubernetes methods now accept and ignore a `_request_timeout` error for better compatibility with the Kubernetes API.
- Add delete, list, and watch support for persistent volume claims to the Kubernetes mock.

### Bug fixes

- `safir.database.datetime_to_db`, `safir.datetime.format_datetime_for_logging`, and `safir.datetime.isodatetime` now accept any `datetime` object with a time zone whose offset from UTC is 0, rather than only the `datetime.UTC` time zone object.
- `safir.pydantic.normalize_datetime` now explicitly rejects input other than seconds since epoch or datetime objects with a validation error rather than attempting to treat the input as a datetime object and potentially throwing more obscure errors.
- The `_request_timeout` parameters to mock Kubernetes methods now accept a float instead of an int to more correctly match the types of kubernetes_asyncio. The mock still does not accept a tuple of timeouts.
- Avoid reusing the same metadata object when creating a `Pod` from a `Job`. Previous versions modified the `spec` part of the `Job` when adding additional metadata to the child `Pod`.

### Other changes

- Safir is now tested with Python 3.12 as well as Python 3.11.

<a id='changelog-4.5.0'></a>
## 4.5.0 (2023-09-12)

### New features

- Add `list_namespaced_custom_object` with watch support to the Kubernetes mock.
- Add watch, field selector, and label selector support to `list_namespace` in the Kubernetes mock.

### Bug fixes

- The Kubernetes mock now correctly maintains the resource version of `Ingress`, `Job`, and `Service` objects, since they support watches which rely on resource versions.
- When creating a `Pod` from a `Job` in the Kubernetes mock using `generateName`, randomize the `Pod` name like Kubernetes does rather than using a fixed name. This forces tests to scan correctly for pods associated with a job. If the `Pod` `name` or `generateName` was explicitly configured in the `Job` template, honor it.
- `read_namespace` and `list_namespace` in the Kubernetes mock now only return namespace objects that have been explicitly created, not implicit namespaces created by creating another object without making a namespace first. This more closely matches the behavior of Kubernetes while still making it easy to use the mock in a test environment simulating a pre-existing namespace.

<a id='changelog-4.4.0'></a>
## 4.4.0 (2023-09-07)

### New features

- Add a `safir.click.display_help` helper function that implements a `help` command for Click-based command-line interfaces, with support for nested subcommands.
- Add a new `safir.asyncio.AsyncMultiQueue` data structure, which is an asyncio multi-reader queue that delivers all messages to each reader independently.
- Add `read_` methods for the Kubernetes object types for which the mock provided `create_` methods (`NetworkPolicy` and `PersistentVolumeClaim`).

### Bug fixes

- Fix typing of the `safir.asyncio.run_with_asyncio` decorator so that it doesn't mask the type of the underlying function.
- Kubernetes objects included in events are now serialized properly using the Kubernetes camel-case field names instead of the Python snake-case names. In addition to matching Kubernetes behavior more closely, this allows a watch configured with the Kubernetes model type to deserialize the object in the `object` key of the event dictionary. The type must be passed explicitly to the `Watch` constructor, since kubernetes_asyncio's type autodetection does not work with Safir's mock.
- `safir.testing.kubernetes.patch_kubernetes` no longer mocks the entire `ApiClient` class since it is required for deserialization of objects in Kubernetes events. It instead mocks the `request` method of that class for safety, to prevent any network requests to Kubernetes clusters when Kubernetes is mocked.

### Other changes

- Safir now uses the [Ruff](https://docs.astral.sh/ruff/) linter instead of flake8 and isort.

<a id='changelog-4.3.1'></a>
## 4.3.1 (2023-07-17)

### Bug fixes

- Safir now pins the major version of all of its non-development dependencies. The impetus for this change is to prevent upgrades to Pydantic 2.x until Safir's Pydantic models are ready for that upgrade, but a similar principle applies to other dependencies. These pins will be selectively relaxed once Safir has been confirmed to work with a new major release.

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
- `safir.metadata.get_metadata` now returns a [Pydantic](https://docs.pydantic.dev/latest/) model.

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
