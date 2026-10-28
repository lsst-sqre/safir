:og:description: Learn how to manage application settings for a database

.. py:currentmodule:: safir.database

###############################
Database configuration settings
###############################

Safir provides settings classes based on `Pydantic BaseSettings`_ for configuring the database used by an application.
The simplest approach for most applications is to use these classes as part of their overall configuration, conventionally as a ``database`` attribute of the main application ``Config`` class.

Applications that use PostgreSQL with these settings classes will be able to transparently support either an external PostgreSQL instance or a Cloud SQL instance.
The settings classes and the :doc:`engine management interface <engine>` will use these settings to connect to the external database using the appropriate protocol, and the rest of the application can ignore the underlying differences.

.. _db-using-settings:

Using the settings classes
==========================

The two settings classes are `DatabaseSettings`, which is used for a conventional external database with an associated DSN and password, and `CloudSqlSettings`, which is used for a Cloud SQL PostgreSQL instance.
The `CloudSqlSettings` class usually be used as-is.
The `DatabaseSettings` class normally must be subclassed to set an environment variable prefix so that the password can be provided via an environment variable.

When using the Safir database support, applications should use YAML for their configuration.
Choosing between Cloud SQL and an external database based on the configuration can be done more smoothly by validating a YAML file than by attempting to shove the same structure into environment variables.

Here is a typical example of an application with a database to configure:

.. code-block:: python

   from typing import Annotated

   from pydantic import Field
   from pydantic_settings import BaseSettings, SettingsConfigDict
   from safir.database import CloudSqlSettings, DatabaseSettings


   class ExampleDatabaseSettings(DatabaseSettings):
       model_config = SettingsConfigDict(env_prefix="EXAMPLE_DATABASE_")


   class Config(BaseSettings):
       ...

       database: Annotated[
           CloudSqlSettings | ExampleDatabaseSettings,
           Field(title="Database configuration"),
       ]

The child class exists only to override ``env_prefix`` so that you can configure the database password (and the URL, which is useful for tests) with the ``EXAMPLE_DATABASE_PASSWORD`` environment variable.
Change ``EXAMPLE`` and ``Example`` to something appropriate for your application.

``config.database`` can then be passed into `engine_manager`, which will use those settings to set up the database engine.
See :doc:`engine` for more details.

Supported settings
==================

External databases
------------------

External databases must be configured with a URL (a DSN) and a password.
Normally, the URL is provided directly in the application configuration and the password is injected via a secret.
For example:

.. code-block:: yaml

   config:
     database:
       url: "postgresql://example@db01.example.com/example"

The password is then normally provided in the ``EXAMPLE_DATABASE_PASSWORD`` environment variable, set via a Kubernetes secret.
See :ref:`db-using-settings` for more details.

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
The application can set the values of any parameter, either as a default or as the only supported setting, by subclassing the settings classes and setting that parameter.
For example:

.. code-block:: python

   from typing import Annotated

   from pydantic import Field
   from pydantic_settings import BaseSettings, SettingsConfigDict
   from safir.database import CloudSqlSettings, DatabaseSettings


   class ExampleCloudSqlSettings(CloudSqlSettings):
       isolation_level: str = "REPEATED READ"


   class ExampleDatabaseSettings(DatabaseSettings):
       model_config = SettingsConfigDict(env_prefix="EXAMPLE_DATABASE_")

       isolation_level: str = "REPEATED READ"


   class Config(BaseSettings):
       ...

       database: Annotated[
           ExampleCloudSqlSettings | ExampleDatabaseSettings,
           Field(title="Database configuration"),
       ]

Technically, this sets a default that can still be overridden in the YAML configuration file.
This generally does not matter in practice; if that setting is not documented, no one will have a reason to set it in the configuration in the Helm chart.
