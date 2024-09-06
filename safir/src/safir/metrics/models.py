"""Models for representing metrics events."""

from dataclasses_avroschema.pydantic import AvroBaseModel
from pydantic import UUID4, AwareDatetime, Field


class EventMetadata(AvroBaseModel):
    """Base model for all events emitted by this service.

    Contains the minimum required fields.
    """

    id: UUID4 = Field(
        title="id",
        description="A globally unique value that identifies this event",
    )

    service: str = Field(
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
        description=("The number of nanoseconds since the unix epoch"),
    )


class Payload(AvroBaseModel):
    """All event payloads should inherit from this."""

    def validate_structure(self) -> None:
        """Do runtime validation of fields.

        Make sure all of the fields are compatible with the backing datastore
        (InfluxDB at the time of this writing).
        """
