#############################
Utilities for Pydantic models
#############################

Several validation and configuration problems arise frequently with Pydantic models.
Safir offers some utility functions to assist in solving them.

.. _pydantic-dsns:

Configuring PostgreSQL and Redis DSNs
=====================================

Databases and other storage services often use a :abbr:`DSN (Data Source Name)` to specify how to connect to the service.
Pydantic provides multiple pre-defined types to parse and validate those DSNs, including ones for PostgreSQL and Redis.

Safir applications often use tox-docker_ to start local PostgreSQL and Redis servers before running tests.
tox-docker starts services on random loopback IP addresses and ports, and stores the hostname and IP address in standard environment variables.

Safir provides alternative data types for PostgreSQL and Redis DSNs that behave largely the same as the Pydantic data types if the tox-docker environment variables aren't set.
If the tox-docker variables are set, their contents are used to override the hostname and port of any provided DSN with the values provided by tox-docker.
This allows the application to get all of its configuration from environment variables at module load time without needing special code in every application to handle the tox-docker environment variables.

For PostgreSQL DSNs, use the data type `safir.pydantic.EnvAsyncPostgresDsn` instead of `pydantic.PostgresDsn`.
This type additionally forces the scheme of the PostgreSQL DSN to either not specify the underying library or to specify asyncpg, allowing it to work correctly with the :doc:`Safir database API <database/index>`.
Unlike the Pydantic type, `~safir.pydantic.EnvAsyncPostgresDsn` only supports a single host.

For Redis DSNs, use the data type `safir.pydantic.EnvRedisDsn` instead of `pydantic.RedisDsn`.

For example:

.. code-block:: python

   from pydantic_settings import BaseSettings, SettingsConfigDict
   from safir.pydantic import EnvAsyncPostgresDsn, EnvRedisDsn


   class Config(BaseSettings):
       model_config = SettingsConfigDict(
           env_prefix="EXAMPLE_", case_sensitive=False
       )

       database_url: EnvAsyncPostgresDsn
       redis_url: EnvRedisDsn

These types only adjust DSNs initialized as normal.
They do not synthesize DSNs if none are set.
Therefore, the application will still need to set the corresponding environment variables in :file:`tox.ini` for testing purposes, although the hostname and port can be dummy values.
In this case, that would look something like:

.. code-block:: ini

   [testenv:py]
   setenv =
       EXAMPLE_DATABASE_URL = postgresql://example@localhost/example
       EXAMPLE_REDIS_URL = redis://localhost/0

.. _pydantic-datetime:

Normalizing datetime fields
===========================

Pydantic supports several input formats for `~datetime.datetime` fields, but the resulting `~datetime.datetime` object may be timezone-naive.
Best practice for Python code is to only use timezone-aware `~datetime.datetime` objects in the UTC time zone.

Safir provides a data type, `~safir.pydantic.UtcDatetime`, that can be used in models.
It is equivalent to `~datetime.datetime` except that it coerces any input to UTC and ensures that it is always timezone-aware.

Here's an example of how to use it:

.. code-block:: python

   from typing import Annotated

   from pydantic import BaseModel, field_validator
   from safir.pydantic import UtcDatetime


   class Info(BaseModel):
       last_used: Annotated[
           UtcDatetime | None,
           Field(
               title="Last used",
               description="When last used",
               examples=[1614986130, "2021-03-05T15:15:30+00:00"],
           ),
       ]

This data type accepts all of the input formats that Pydantic accepts.

IVOA DALI timestamps
--------------------

In some cases, such as services that implement IVOA standards, it may be desirable to require input timestamps compatible with the `IVOA DALI`_ standard.

.. _IVOA DALI: https://www.ivoa.net/documents/DALI/20170517/REC-DALI-1.1.html

This can be done using `~safir.pydantic.IvoaIsoDatetime` as the data type instead of `~safir.pydantic.UtcDatetime`.
This data type produces the same timezone-aware UTC `~datetime.datetime` objects, but it only accepts ``YYYY-MM-DD[THH:MM:SS[.mmm]][Z]`` as the input format.

Following the IVOA DALI standard, the trailing ``Z`` is optional, but the timestamp is always interpreted as UTC.
Explicit timezone information is not allowed.

.. _pydantic-timedelta:

Normalizing timedelta fields
============================

The default Pydantic validation for `datetime.timedelta` fields accepts either a floating-point number of seconds or an ISO 8601 duration as a string.
The syntax for ISO 8601 durations is unambiguous but obscure.
For example, ``P23DT23H`` represents a duration of 23 days and 23 hours.

Safir provides two alternate data types for Pydantic models.
Both of these types represent normal `~datetime.timedelta` objects with some Pydantic validation rules attached.
They can be used in Python source exactly like `~datetime.timedelta` objects.

The type `safir.pydantic.SecondsTimedelta` accepts only a floating-point number of seconds, but allows it to be given as a string.
For example, input of either ``300`` or ``"300"`` becomes a `~datetime.timedelta` object representing five minutes (300 seconds).

The type `safir.pydantic.HumanTimedelta` accepts those formats as well as the time interval strings parsed by `safir.datetime.parse_timedelta`.
For example, the string ``3h5m23s`` becomes a `~datetime.timedelta` object representing three hours, five minutes, and 23 seconds.
See :ref:`datetime-timedelta` for the full supported syntax.

These can be used like any other type in a model and perform their validation automatically.
For example:

.. code-block:: python

   from pydantic import BaseModel
   from safir.pydantic import HumanTimedelta, SecondsTimedelta


   class Model(BaseModel):
       timeout: SecondsTimedelta
       lifetime: HumanTimedelta

Accepting camel-case attributes
===============================

Python prefers ``snake_case`` for all object attributes, but some external sources of data (Kubernetes custom resources, YAML configuration files generated from Helm configuration) require or prefer ``camelCase``.

Thankfully, Pydantic supports converting from camel-case to snake-case on input using what Pydantic calls an "alias generator."
Safir provides `~safir.pydantic.to_camel_case`, which can be used as that alias generator.

To use it, add a configuration block to any Pydantic model that has snake-case attributes but needs to accept them in camel-case form:

.. code-block:: python

   from pydantic import BaseModel, ConfigDict
   from safir.pydantic import to_camel_case


   class Model(BaseModel):
       model_config = ConfigDict(
           alias_generator=to_camel_case, populate_by_name=True
       )

       some_field: str

By default, only the generated aliases (so, in this case, only the camel-case form of the attribute, ``someField``) are supported.
The additional setting ``allow_population_by_field_name``, tells Pydantic to allow either ``some_field`` or ``someField`` in the input.

As a convenience, you can instead inherit from `~safir.pydantic.CamelCaseModel`, which is a derived class of `~pydantic.BaseModel` with those settings added.
This is somewhat less obvious when reading the classes and thus less self-documenting, but is less tedious if you have numerous models that need to support camel-case.
`~safir.pydantic.CamelCaseModel` also overrides ``model_dump`` and ``model_dump_json`` to change the default of ``by_alias`` to `True` so that this model exports in camel-case by default.

Requiring exactly one of a list of attributes
=============================================

Occasionally, you will have reason to write a model with several attributes, where one and only one of those attributes may be set.
For example:

.. code-block:: python

   class Model(BaseModel):
       docker: Optional[DockerConfig] = None
       ghcr: Optional[GHCRConfig] = None

The intent here is that only one of those two configurations will be present: either Docker or GitHub Container Registry.
However, Pydantic has no native way to express that, and the above model will accept input where neither or both of those attributes are set.

Safir provides a function, `~safir.pydantic.validate_exactly_one_of`, designed for this case.
It takes a list of fields, of which exactly one must be set, and builds a model validator function that checks this property of the model.

So, in the above example, the full class would be:

.. code-block:: python

   from pydantic import BaseModel, model_validator
   from safir.pydantic import validate_exactly_one_of


   class Model(BaseModel):
       docker: Optional[DockerConfig] = None
       ghcr: Optional[GHCRConfig] = None

       _validate_type = model_validator(mode="after")(
           validate_exactly_one_of("docker", "ghcr")
       )

Note the syntax, which is a little odd since it is calling a decorator on the results of a function builder.
