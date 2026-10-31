:og:description: Learn how to use Safir's application configuration support.

#########################
Application configuration
#########################

The recommended configuration pattern for applications using Safir is to create a ``Config`` class that encapsulates the (possibly multi-level) configuration model for the application.

There are two common ways of populating that class: use environment variables to create a global ``Config`` object on module load, or load the configuration on startup from a YAML configuration file.
Configuring only with environment variables is straightforwardly supported by `Pydantic BaseSettings`_.
Safir provides additional support for those applications that want to use YAML.

When to use YAML
================

Applications should consider using YAML if:

- the configuration involves nested or complex data structures that would otherwise have to be serialized; or
- there are numerous configuration settings, so providing a portion of the Helm :file:`values.yaml` file directly to the application as a configuration file is less tedious than adding numerous environment variables.

.. _config-define:

Defining the configuration
==========================

To use YAML for configuration, define the ``Config`` class (conventionally in :file:`config.py` at the top level of the application source tree) as inheriting from `safir.pydantic.YamlBaseSettings`.

If the application gets any of its configuration, such as parameters provided as secrets, from environment variables, the application should also define an environment variable prefix.
For example:

.. code-block:: yaml
   :caption: config.py

   from pydantic_settings import SettingsConfigDict
   from safir.pydatic import YamlBaseSettings

   class Config(YamlBaseSettings):
       model_config = SettingsConfigDict(env_prefix="EXAMPLE_")

       # ... define configuration settings here

Any nested models pointed to by attributes of ``Config`` should normally inherit from ``BaseModel``, **not** from ``BaseSettings`` or ``YamlBaseSettings``.
This ensures that only environment variables that respect the ``env_prefix`` and ``env_nested_delimiter`` settings in the ``Config`` class.
Nested models should only inherit from ``BaseSettings`` if they want to take values from separate environment variables that do not follow the prefix rules of the main application configuration.

Any nested models should use ``pydantic.alias_generators.to_camel`` as an alias generator so that they respect the Helm camel-case convention for settings.
For example:

.. code-block:: yaml
   :caption: config.py

   from pydantic import AliasGenerator, BaseModel, ConfigDict
   from pydantic.alias_generators import to_camel
   from pydantic_settings import SettingsConfigDict
   from safir.pydatic import YamlBaseSettings

   class SubsystemConfig(BaseModel):
       model_config = ConfigDict(
           alias_generator=AliasGenerator(validation_alias=to_camel),
           extra="forbid",
           validate_by_name=True,
       )

       parameter: str

   class Config(YamlBaseSettings):
       model_config = SettingsConfigDict(
           env_nested_delimiter="__",
           env_prefix="EXAMPLE_",
       )

       subsystem: SubsystemConfig

Note the value of ``env_nested_delimiter`` above.
The environment variable used to set ``subsystem.parameter`` will therefore be ``EXAMPLE_SUBSYSTEM__PARAMETER`` with a double underscore before the nested model, and the Helm chart for the application should be written accordingly.
This is the recommended way of handling nested configuration settings that should be set by environment variable.
Do not attempt to use a single underscore.
It will break horribly if any of the submodel parameters contain underscores.

Providing the configuration
===========================

By convention, the contents of the ``config`` key of an application's Helm :file:`values.yaml` file should be provided to the application as its YAML configuration.
This enforces by convention the useful property that settings used by the application itself go under ``config``, and other settings are used by the Helm chart or other components of the application setup.

This is usually done with a simple ``ConfigMap`` resource, such as:

.. code-block:: yaml

   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: "example"
     labels:
       {{- include "example.labels" . | nindent 4 }}
   data:
     config.yaml: |
       {{- toYaml .Values.config | nindent 4 }}

Then, in the pod specification, mount this config map inside the pod.
By convention, :file:`/etc/{application}` is usually used as the mount point.
For example:

.. code-block:: yaml

   apiVersion: apps/v1
   kind: Deployment:
   # ...
   spec:
     # ...
     template:
       spec:
         containers:
           - name: "{{ Chart.name }}"
             # ...
             volumeMounts:
               - name: "config"
                 mountPath: "/etc/example"
                 readOnly: true
         # ...
         volumes:
           - name: "config"
             configMap:
               name: "example"

For any configuration setting that needs to come from another source, such as a secret or a dynamic calculation, set the corresponding environment variable as determined by the ``env_prefix`` setting used in the ``Config`` class you defined in :ref:`config-define`.

Be aware that `~safir.pydantic.YamlBaseSettings` sets ``extra="forbid"``.
Unless you override that in your application, every key under ``config`` in the Helm :file:`values.yaml` file must be a valid configuration setting for the application.
The application can ignore the setting, but it needs to be defined in its ``Config`` model.
This is normally desired since it provides typo protection: Setting an invalid parameter in a :file:`values.yaml` file will cause the application to fail to start.
However, you will sometimes need to add dummy application settings so that you can accomodate :file:`values.yaml` settings that are not used directly but that feel like they belong under ``config``.

Using the configuration
=======================

Creating the configuration dependency
-------------------------------------

The recommended way to manage the configuration of a FastAPI application is to use a FastAPI dependency that loads the configuration on demand and returns it to any route that needs it.
Safir provides a generic dependency that can be initialized with any configuration model.

To create a configuration dependency for an application, call `safir.dependencies.config.ConfigDependency` with the configuration model, the default path (which should be where the configuration will be mounted in Kubernetes pods), and the environment variable used to override the configuration path.
The result will be an object that can be used as a FastAPI dependency and will load the configuration on demand.

For example:

.. code-block:: python

   from safir.dependencies.config import ConfigDependency

   config_dependency = ConfigDependency(
       Config, "/etc/example/config.yaml", "EXAMPLE_CONFIG"
   )

The most convenient place to put this definition is at the bottom of :file:`config.py` where the configuration is defined.
Alternately, if you want to group all FastAPI dependencies together, you can put this code in :file:`dependencies/config.py` in the application source tree.

Using the configuration dependency
----------------------------------

Once the configuration dependency has been defined, it can be used in any FastAPI route as a dependency.
For example:

.. code-block:: python

   from typing import Annotated

   from fastapi import Depends

   from ..config import Config, config_dependency


   @router.get("/")
   async def some_route(
       config: Annotated[Config, Depends(config_dependency)],
   ) -> SomeModel: ...

Code outside of the FastAPI application that needs the application configuration can call the `~safir.dependencies.config.ConfigDependency.config` method directly to get the configuration model.

Configuration during application startup
----------------------------------------

Special care is needed during application startup.
The configuration may be needed to fully configure the application.
For example, structlog_ settings are usually based on the application configuration, and sometimes middleware and router decisions should be based on configuration settings.
Most FastAPI examples show fully configuring the application on module load, but this is too early for a test suite that needs to override the default configuration path to a path dynamically determined from the location of the test data.
It is therefore important to defer loading the configuration until the test suite has had a chance to change the configuration path.

The easiest way to do this is to move the FastAPI application creation into a callable instead of creating the application on module load.
For example:

.. code-block:: python

   from collections.abc import AsyncGenerator
   from contextlib import asynccontextmanager
   from importlib.metadata import metadata, version

   import structlog
   from fastapi import FastAPI
   from safir.logging import configure_logging, configure_uvicorn_logging
   from safir.slack.webhook import SlackRouteErrorHandler


   def create_app(*, load_config: bool = True) -> FastAPI:
       config = None
       if load_config:
           config = config_dependency.config()
           configure_logging(
               profile=config.log_profile,
               log_level=config.log_level,
               name="example",
           )
           configure_uvicorn_logging(config.log_level)
           path_prefix = config.path_prefix
       else:
           path_prefix = "/example"

       app = FastAPI(
           title="example",
           description=metadata("example")["Summary"],
           version=version("example"),
           openapi_url=f"{path_prefix}/openapi.json",
           docs_url=f"{path_prefix}/docs",
           redoc_url=f"{path_prefix}/redoc",
       )
       app.include_router(internal_router)
       app.include_router(external_router, prefix=f"{path_prefix}")

       if config and config.slack_webhook:
           logger = structlog.get_logger("example")
           SlackRouteErrorHandler.initialize(
               config.slack_webhook, "example", logger
           )
           logger.debug("Initialized Slack webhook")

Then, change :file:`Dockerfile` for your application (or wherever else your application is started) to pass the ``--factory`` flag to Uvicorn_.

.. code-block:: docker

   CMD ["uvicorn", "--factory", "example.main:create_app", "--host", "0.0.0.0", "--port", "8080"]

Generating an OpenAPI specification
-----------------------------------

Notice the boolean parameter ``load_config`` in the above ``create_app`` function.
This parameter allows the application's FastAPI object to be created using a default path prefix without needing a full application configuration.
This is required if you want to be able to generate an OpenAPI specification for the application without providing a configuration file, such as during the documentation build process.
With the above ``create_app`` function, you can do that with a function like:

.. code-block:: python

   def create_openapi() -> str:
       app = create_app(load_config=False)
       return json.dumps(
           get_openapi(
               title=app.title,
               version=app.version,
               description=app.description,
               routes=app.routes,
           )
       )

You can then point the Sphinx at that function to generate the OpenAPI specification.
See the `Documenteer documentation <https://documenteer.lsst.io/guides/openapi.html>`__ for more details.

Testing applications with a YAML configuration
==============================================

Applications that use YAML for configuration will need to provide at least one configuration that will be used by the test suite.
Depending on the application, you may wish to provide several different configurations and allow the test to choose which conifguration to use.

By convention, test application configurations should go in :file:`test/data/config/{name}.yaml`.
Then, use a fixture in :file:`tests/conftest.py` to set the configuration path, overriding the default that is only appropriate for Kubernetes pods:

.. code-block:: python

   import pytest

   from example.config import Config, config_dependency


   @pytest.fixture(autouse=True)
   def config(data: Data, monkeypatch: pytest.MonkeyPatch) -> Config:
       # use monkeypatch.setenv to set any needed environment variables
       config_path = data.path("config/default.yaml")
       config_dependency.set_config_path(config_path)
       return config_dependency.config()

Here, this fixture is set to autouse to ensure the configuration is set up before any tests run.
You can instead have appropriate application fixtures depend on this fixture instead.
Any test that needs access to the application configuration can also explicitly request the fixture and get back the parsed configuration model.

The test configuration is located using `safir.testing.data.Data`.
See :doc:`/user-guide/test-data` for more details.

Often, you will have multiple test configurations and some tests will need a non-default configuration.
In this case, use a slightly more complex fixture that supports parametrization with the desired configuration.

.. code-block:: python

   import pytest

   from example.config import Config, config_dependency


   @pytest.fixture(autouse=True, params=["default"])
   def config(
       data: Data,
       monkeypatch: pytest.MonkeyPatch,
       request: pytest.FixtureRequest,
   ) -> Config:
       # use monkeypatch.setenv to set any needed environment variables
       config_path = data.path(f"config/{request.param}.yaml")
       config_dependency.set_config_path(config_path)
       return config_dependency.config()

With this fixture, any test that does not take any special actions will use the :file:`tests/data/default.yaml` configuration.
A test that needs a different configuration should use indirect fixture parametrization:

.. code-block:: python

   import pytest


   @pytest.mark.parametrize("config", ["other"], indirect=True)
   def test_something() -> None: ...

This test will use :file:`tests/data/other.yaml` as the application configuration instead.
Note that the test does not have to request the ``config`` fixture directly to parametrize it in this way.
See the `pytest documentation <https://docs.pytest.org/en/stable/example/parametrize.html#indirect-parametrization>`__ for more details on indirect fixture parametrization.
