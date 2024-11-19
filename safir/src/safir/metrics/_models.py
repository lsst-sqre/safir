"""Models for representing metrics events."""

from typing import Any

from dataclasses_avroschema.pydantic import AvroBaseModel
from pydantic import UUID4, AwareDatetime, Field, create_model

__all__ = ["EventMetadata", "EventPayload"]


class EventMetadata(AvroBaseModel):
    """Common fields for all metrics events.

    Contains the minimum required fields. This gets mixed in
    to a class also containing event payload fields, and
    then gets shipped to Kafka, by the ``EventManager``
    """

    id: UUID4 = Field(
        title="id",
        description="A globally unique value that identifies this event",
    )

    application: str = Field(
        description="The application generating this event.",
        examples=["gafaelfawr", "mobu"],
    )

    timestamp: AwareDatetime = Field(
        description=(
            "The time at which this event occurred, or the time at which this"
            " event completed if it is a duration event."
        ),
    )

    timestamp_ns: int = Field(
        description=(
            "The number of nanoseconds since the unix epoch. This is used as"
            " the InfluxDB timestamp."
        ),
    )


class EventPayload(AvroBaseModel):
    """All event payloads should inherit from this."""

    @classmethod
    def validate_structure(cls) -> None:
        """Do runtime validation of fields.

        Make sure all of the fields are compatible with the backing datastore
        (InfluxDB at the moment).
        """
        valids = [
            "boolean",
            "double",
            "enum",
            "float",
            "int",
            "long",
            "null",
            "string",
        ]
        errors = []

        # Calling cls.avro_schema_to_python() sets a _metadata class variable
        # on this class that memoizes the metadata that comes from any inner
        # Meta class:
        # (https://marcosschroh.github.io/dataclasses-avroschema/records/?h=meta#class-meta)
        #
        # We don't have a Meta class on this payload, but later, we mix this
        # payload into another class that DOES have an inner Meta class that
        # contains the schema name and namespace. If _metadata is already set
        # on this class, that later class will not get that metadata when we
        # eventually call avro_schema_to_python on it.
        #
        # This makes a throw-away class where _metadata will get set, which
        # means the metadata will be generated fresh on the big mixed-in class
        # when we need it.
        tmp_cls = create_model("Temp", __base__=cls)

        schema = tmp_cls.avro_schema_to_python()
        for field in schema["fields"]:
            field_type = field["type"]
            name = field["name"]

            # Unions are represented by a list
            if isinstance(field_type, list):
                if not all(
                    cls._extract_type(subtype) in valids
                    for subtype in field_type
                ):
                    errors.append(
                        f"{name}\n   is a union with a type that is"
                        f" unsupported by InfluxDB: {field_type}"
                    )
                continue

            field_type = cls._extract_type(field_type)

            if field_type not in valids:
                errors.append(
                    f"{name}\n   Serializes to an avro type that is"
                    f" unsupported by InfluxDB: {field_type}"
                )

        if errors:
            errors = ["Unsupported Avro Schema", *errors]
            errors.append(
                f"Supported avro types are these (or unions of these):"
                f" {valids}"
            )
            raise ValueError("\n".join(errors))

    @classmethod
    def _extract_type(cls, spec: str | dict[str, dict[str, Any]]) -> str:
        """Extract avro base type from container type.

        Raises
        ------
        ValueError
           If a base type can not be extracted
        """
        # Some complex types like enums are represented by a dict, not a
        # string.
        avro_type: str | dict = spec
        if isinstance(spec, dict):
            avro_type = spec["type"]
        if not isinstance(avro_type, str):
            # Ignore suggestion to make this a type error to keep consistent
            # with the ValueError in the calling method.
            raise ValueError(f"{spec} is not a supported Avro type")  # noqa: TRY004
        return avro_type
