"""Schema manager exceptions."""

__all__ = ["UnmanagedSchemaError"]


class UnmanagedSchemaError(Exception):
    """When a schema is not managed by the Registry, and therefore cannot be
    serialized into a native Python object.
    """


class InvalidAvroNameError(Exception):
    """When the decalred name or namespace for an Avro schema is not valid
    according to https://avro.apache.org/docs/1.11.1/specification/#names .
    """
