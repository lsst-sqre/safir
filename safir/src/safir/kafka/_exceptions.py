"""Schema manager exceptions."""

__all__ = [
    "IncompatibleSchemaError",
    "InvalidAvroNameError",
    "InvalidMetadataError",
    "UnknownDeserializeError",
    "UnknownSchemaError",
]


from dataclasses_avroschema.pydantic import AvroBaseModel


class IncompatibleSchemaError(Exception):
    """A schema is incompatible with the latest version in the registry."""


class InvalidAvroNameError(Exception):
    """The decalred name or namespace for an Avro schema is not valid."""


class InvalidMetadataError(Exception):
    """The Meta inner class on a model has unexpected values in fields."""


class UnknownDeserializeError(Exception):
    """The schema registry client returns None when deserializing."""


class UnknownSchemaError(Exception):
    """A schema is not managed by the Registry, and therefore cannot be
    serialized into a native Python object.
    """

    def __init__(self, data: AvroBaseModel, subject: str) -> None:
        self.message = (
            f"Schema for model: {type(data).__name__} with subject: {subject}"
            " is not known to the manager. ``register`` must be called before"
            " you try to serialize instances of this model."
        )
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message
