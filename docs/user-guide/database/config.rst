:og:description: Learn how to manage application settings for a database

.. py:currentmodule:: safir.database

######################
Database configuration
######################

Safir provides Pydantic models for configuring the database used by an application.
Applications that use PostgreSQL with these models will be able to transparently support either an external PostgreSQL instance or a Cloud SQL instance.
The :doc:`engine management interface <engine>` will use these models to connect to the external database using the appropriate protocol, and the rest of the application can ignore the underlying differences.

The simplest approach for most applications is to use these classes as part of the application configuration model, conventionally as a ``database`` attribute of the main application ``Config`` class.
``config.database`` can then be passed into `engine_manager`, which will use those models to set up the database engine.

.. _db-using-config:

Using the configuration models
==============================

The two models are `DatabaseConfig`, which is used for a conventional external database with an associated DSN and password, and `CloudSqlConfig`, which is used for a Cloud SQL PostgreSQL instance.

YAML-based configuration
------------------------

Applications that read their configuration from a YAML file (see :doc:`/user-guide/config`) will use a pattern such as the following:

.. code-block:: python

   from typing import Annotated

   from pydantic import Field
   from pydantic_settings import SettingsConfigDict
   from safir.database import CloudSqlConfig, DatabaseConfig
   from safir.pydantic import YamlBaseSettings


   class Config(YamlBaseSettings):
       model_config = SettingsConfigDict(
           env_nested_delimiter="__", env_prefix="EXAMPLE_"
       )

       # ...

       database: Annotated[
           CloudSqlConfig | DatabaseConfig,
           Field(title="Database configuration"),
       ]

Change ``EXAMPLE_`` to something appropriate for your application.

Most fields will then be automatically parsed from the ``database`` key in the YAML file, which corresponds to the ``config.database`` key in the Helm :file:`values.yaml` file.

When not using Cloud SQL, the database password will have to be injected via a secret.
For some applications, it may also be desirable to inject the database URL via an environment variable, such as when the application is configured to use Phalanx in-cluster PostgreSQL.
To do this, set the environment variables ``EXAMPLE_DATABASE__PASSWORD`` and ``EXAMPLE_DATABASE__URL`` (note the double underscores).
This will override anything set in the YAML file.

.. _database-config-env:

Environment-based configuration
-------------------------------

Configuration for applications that use environment variables for all settings instead of a YAML file is very similar:

.. code-block:: python

   from typing import Annotated

   from pydantic import Field
   from pydantic_settings import BaseSettings, SettingsConfigDict
   from safir.database import CloudSqlConfig, DatabaseConfig


   class Config(BaseSettings):
       model_config = SettingsConfigDict(
           env_nested_delimiter="__", env_prefix="EXAMPLE_"
       )

       # ...

       database: Annotated[
           CloudSqlConfig | DatabaseConfig,
           Field(title="Database configuration"),
       ]

The only difference is using regular `Pydantic BaseSettings`_ as the base class for ``Config``.
Change ``EXAMPLE_`` to something appropriate for your application.

The database configuration can then be passed from the Helm :file:`values.yaml` file in one of two ways:

- Pass the entire ``config.database`` portion of :file:`values.yaml` to the application in an environment variable, encoded in JSON.
  For this approach, put the following line in the ``data`` section of the application ``ConfigMap`` where the other configuration environment variables are set::

    EXAMPLE_DATABASE: {{ toJson .Values.config.database | quote }}

  The resulting JSON will then be parsed by Pydantic and interpreted as either `CloudSqlConfig` or `DatabaseConfig`, depending on which schema it satisfies.

- Use individual environment variables to pass in all of the possible settings.
  This is more tedious, since you will have to replicate all the possible attributes for either `CloudSqlConfig` or `DatabaseConfig` (including their shared base class) that you want to support in the Helm :file:`values.yaml` file in the ``ConfigMap``.
  The results will look something like::

    EXAMPLE_DATABASE__TYPE: {{ .Values.config.database.type | quote }}
    {{- if .Values.config.database.url }}
    EXAMPLE_DATABASE__URL: {{ .Values.config.database.url | quote }}
    {{- end }}
    {{- if eq .Values.config.database.type "cloudsql" }}
    EXAMPLE_DATABASE__PROJECT:: {{ .Values.config.database.project | quote }}
    EXAMPLE_DATABASE__REGION:: {{ .Values.config.database.region | quote }}
    EXAMPLE_DATABASE__INSTANCE:: {{ .Values.config.database.database | quote }}
    EXAMPLE_DATABASE__DATABASE:: {{ .Values.config.database.instance | quote }}
    EXAMPLE_DATABASE__SERVICE_ACCOUNT:: {{ .Values.config.database.serviceAccount | quote }}
    {{- end }}

  Any other supported settings will need their own lines.
  Note the double underscores.

  If you use this approach, you will need to update ``ConfigMap`` for any additional settings that you want to support.

In both cases, change ``EXAMPLE_`` as appropriate for your application.

Supported settings
==================

All of the example configurations in the following sections are excerpts from a hypothetical :file:`values.yaml` file in Phalanx_ for an application.

External databases
------------------

External databases must be configured with a URL (a DSN) and a password.
Normally, the URL is provided directly in the application configuration and the password is injected via a secret.
For example:

.. code-block:: yaml

   config:
     database:
       url: "postgresql://example@db01.example.com/example"

The password is then normally provided in the ``EXAMPLE_DATABASE__PASSWORD`` (note the double underscore) environment variable, set via a Kubernetes secret.
See :ref:`db-using-config` for more details.

Cloud SQL database
------------------

To configure a Cloud SQL database backend, more parameters must be provided:

``type``
    Must be set to ``cloudsql``.
    The default is ``external``, which is used for an external database configured with a URL and password as above.

``project``
    The Google Cloud Platform project in which the database is located.

``region``
    The Google Cloud Platform region in which the database is located.

``instance``
    The Cloud SQL database instance name.

``database``
    The name of the Cloud SQL database to use within that instance.

``serviceAccount``
    The Google Cloud Platform service account that will be used to access the database.
    This must be the service account to which the running application is mapped using Kubernetes workload identity.

See :doc:`cloudsql` for more details about the recommended way to configure Cloud SQL databases for use with applications that use Safir.

The database configuration when the application is using Cloud SQL will look like this:

.. code-block:: yaml

   config:
     database:
       type: "cloudsql"
       project: "project-7696"
       region: "us-central1"
       instance: "database-e9e11de2"
       database: "example"
       serviceAccount: "example@project-7696.iam.gserviceaccount.com"

Additional database settings
----------------------------

Both `CloudSqlSettings` and `DatabaseSettings` support a variety of common database settings that an application may want to configure.

``isolationLevel``
    The transaction isolation level to use for the database.
    This must be one of the isolation levels supported by the SQLAlchemy database driver in use.

``maxOverflow``
    Maximum connections above the pool size that can be created to handle surge traffic.

``poolPrePing``
    If true, check that a connection is alive before returning it to a session.
    Applications with low traffic whose database connections often time out should consider setting this to true.

``poolRecycle``
    If set, discard any idle connection that has been open for longer than this number of seconds.
    If the connection idle timeout for the database is known, set this value to something slightly shorter.

``poolSize``
    The database connection pool size; the number of connections to the database to keep open.
    Remember that if your application uses multiple replicas, this is the size of the connection pool for each replica, so the total number of open connections will be this number multiplied by the replica count.

``poolTimeout``
    How long to wait for a connection from the connection pool, in seconds.

All of these settings are optional.
If not set, the SQLAlchemy default will be used.

Not all of these settings will make sense to document in the Helm chart for every application.
For example, if an application needs a custom ``isolationLevel``, it will normally want to set that directly in the application, not require that it be set in a Helm chart.
The application can set the values of any parameter, either as a default or as the only supported setting, by subclassing the configuration models and setting that parameter.
For example:

.. code-block:: python

   from typing import Annotated

   from pydantic import Field
   from pydantic_settings import BaseSettings, SettingsConfigDict
   from safir.database import CloudSqlConfig, DatabaseConfig


   class ExampleCloudSqlConfig(CloudSqlConfig):
       isolation_level: str = "REPEATED READ"


   class ExampleDatabaseConfig(DatabaseConfig):
       isolation_level: str = "REPEATED READ"


   class Config(BaseSettings):
       model_config = SettingsConfigDict(
           env_nested_delimiter="__", env_prefix="EXAMPLE_"
       )

       # ...

       database: Annotated[
           ExampleCloudSqlConfig | ExampleDatabaseConfig,
           Field(title="Database configuration"),
       ]

Technically, this sets a default that can still be overridden via a YAML configuration file or an environment variable.
This generally does not matter in practice; if that setting is not documented, no one will have a reason to set it in the configuration in the Helm chart.
