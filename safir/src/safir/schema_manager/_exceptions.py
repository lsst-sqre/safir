"""Schema manager exceptions."""

__all__ = [
    "InvalidAvroNameError",
    "InvalidMetadataError",
    "UnknownDeserializeError",
    "UnknownSchemaError",
    "IncompatibleSchemaError",
]


class UnknownSchemaError(Exception):
    """A schema is not managed by the Registry, and therefore cannot be
    serialized into a native Python object.
    """


class InvalidAvroNameError(Exception):
    """The decalred name or namespace for an Avro schema is not valid."""


class UnknownDeserializeError(Exception):
    """The schema registry client returns None when deserializing."""


class InvalidMetadataError(Exception):
    """The Meta inner class on a model has unexpected values in fields."""


class IncompatibleSchemaError(Exception):
    """A schema is incompatible with the latest version in the registry."""
