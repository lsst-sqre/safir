#############################
Utilities for Pydantic models
#############################

Several validation and configuration problems arise frequently with Pydantic models.
Safir offers some utility functions to assist in solving them.

.. _pydantic-datetime:

Normalizing datetime fields
===========================

Pydantic supports several input formats for `~datetime.datetime` fields, but the resulting `~datetime.datetime` object may be timezone-naive.
Best practice for Python code is to only use timezone-aware `~datetime.datetime` objects in the UTC time zone.

Pydantic provides a utility function, `~safir.pydantic.normalize_datetime`, that can be used as a field validator for a `~datetime.datetime` model field.
It ensures that any input is converted to UTC and is always timezone-aware.

Here's an example of how to use it:

.. code-block:: python

   from pydantic import BaseModel, field_validator
   from safir.pydantic import normalize_datetime


   class Info(BaseModel):
       last_used: Optional[datetime] = Field(
           None,
           title="Last used",
           description="When last used in seconds since epoch",
           examples=[1614986130],
       )

       _normalize_last_used = field_validator("last_used", mode="before")(
           normalize_datetime
       )

Multiple attributes can be listed as the initial arguments of `~pydantic.field_validator` if there are multiple fields that need to be checked.

This field validator accepts all of the input formats that Pydantic accepts.
This includes some ambiguous formats, such as an ISO 8601 date without time zone information.
All such dates are given a consistent interpretation as UTC, but the results may be surprising if the caller expected local time.
In some cases, it may be desirable to restrict input to one unambiguous format.

This can be done by using `~safir.pydantic.normalize_isodatetime` as the field validator instead.
This function only accepts ``YYYY-MM-DDTHH:MM[:SS]Z`` as the input format.
The ``Z`` time zone prefix indicating UTC is mandatory.
It is called the same way as `~safir.pydantic.normalize_datetime`.

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
       some_field: str

       model_config = ConfigDict(
           alias_generator=to_camel_case, populate_by_name=True
       )

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
