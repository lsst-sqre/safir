"""Camel-case attribute support for Pydantic models."""

from pydantic import AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel as to_camel_case

__all__ = [
    "CamelCaseModel",
    "to_camel_case",
]


class CamelCaseModel(BaseModel):
    """`pydantic.BaseModel` configured to accept camel-case input.

    This is a convenience class identical to `~pydantic.BaseModel` except with
    an alias generator configured so that it can be initialized with either
    camel-case or snake-case keys. Model exports with ``model_dump`` or
    ``model_dump_json`` also default to exporting in camel-case.
    """

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=to_camel_case, validation_alias=to_camel_case
        ),
        serialize_by_alias=True,
        validate_by_name=True,
    )
