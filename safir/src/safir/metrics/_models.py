"""Models for representing metrics events."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from dataclasses_avroschema.pydantic import AvroBaseModel
from pydantic import (
    UUID4,
    AwareDatetime,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    create_model,
)
from pydantic_core import CoreSchema, core_schema

__all__ = ["EventDuration", "EventMetadata", "EventPayload"]


if TYPE_CHECKING:
    EventDuration = timedelta
else:

    class EventDuration(timedelta):
        """A dataclasses-avroschema-compatible timedelta field that serializes
        to float seconds.

        .. note::

           Models that use fields of this type must be subclasses of
           `~safir.metrics.EventPayload`.

        dataclasses-avroschema has no built-in support for timedelta fields
        (even though Pydantic does), and if you declare one in your event
        payload model, an exception will be thrown when you try to serialize
        it. By declaring your field with this type, you'll be able to use
        timedeltas, and they will serialze to a float number of seconds.

        Examples
        --------
        .. code-block:: python

           from datetime import datetime, timedelta, timezone
           from safir.metrics import EventDuration, EventPayload


           class MyEvent(EventPayload):
               some_field: str = Field()
               duration: EventDuration = Field()


           start_time = datetime.now(timezone.utc)
           do_some_stuff()
           duration: timedelta = datetime.now(timezone.utc) - start_time

           payload = MyEvent(some_field="woohoo", duration=duration)
        """

        @classmethod
        def __get_pydantic_core_schema__(
            cls, source_type: Any, handler: GetCoreSchemaHandler
        ) -> CoreSchema:
            """Pretend we're a timedelta.

            We need this because dataclasses-avroschema explicitly looks for
            this method when trying to serialize a custom Pydantic type.
            """

            def validate(v: Any) -> EventDuration:
                if isinstance(v, timedelta):
                    return EventDuration(seconds=v.total_seconds())
                elif isinstance(v, EventDuration):
                    return v
                else:
                    raise TypeError("Must be a timedelta or EventDuration")

            return core_schema.no_info_after_validator_function(
                validate, core_schema.timedelta_schema()
            )

        def __float__(self) -> float:
            """Convert to a float number of seconds."""
            return self.total_seconds()


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

    # json_encoders is deprecated in Pydantic v2, but dataclasses-avroschema
    # insists that it is defined for custom types, and that the value for a
    # custom type is one of the built-in dataclasses-avroschema base types
    # (which is why __float__ needs to be defined on the EventDuration class):
    #
    # https://github.com/marcosschroh/dataclasses-avroschema/blob/b8f7b8dfa877fea58887e4cd34d34e2ab6551afa/dataclasses_avroschema/fields/fields.py#L1000-L1038
    model_config = ConfigDict(json_encoders={EventDuration: float})

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
                if not all(subtype in valids for subtype in field_type):
                    errors.append(
                        f"{name}\n   is a union with a type that is"
                        f" unsupported by InfluxDB: {field_type}"
                    )
                continue

            # Some complex types like enums are represented by a dict, not a
            # string.
            if isinstance(field_type, dict):
                field_type = field["type"]["type"]

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
