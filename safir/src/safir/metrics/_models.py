"""Models for representing metrics events."""

from dataclasses_avroschema.pydantic import AvroBaseModel
from pydantic import UUID4, AwareDatetime, Field

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

    app_name: str = Field(
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
        schema = cls.avro_schema_to_python()
        for field in schema["fields"]:
            field_type = field["type"]
            name = field["name"]
            if isinstance(field_type, dict):
                field_type = field["type"]["type"]
            if not isinstance(field_type, str):
                errors.append(
                    f"{name}\n   Couldn't validate avro schema"
                    f"compatibility: {field_type}"
                )
            if field_type not in valids:
                errors.append(
                    f"{name}\n   Serializes to an unsupported avro type:"
                    f" {field_type}"
                )
        if errors:
            errors = ["Unsupported Avro Schema", *errors]
            errors.append(f"Supported avro types are: {valids}")
            raise ValueError("\n".join(errors))
