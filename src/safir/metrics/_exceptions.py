"""Metrics exceptions."""

__all__ = [
    "DuplicateEventError",
    "EventManagerUninitializedError",
    "EventManagerUsageError",
    "KafkaTopicError",
    "UnsupportedAvroSchemaError",
]


class EventManagerUsageError(Exception):
    """These exceptions should be raised even in abandonable methods.

    They represent application errors that can and should be fixed, vs. errors
    with infrastructure outside of the application's control, like the
    underlying Kafka infrastructure.
    """


class UnsupportedAvroSchemaError(EventManagerUsageError):
    """Event model is not serializable to Avro."""


class EventManagerUninitializedError(EventManagerUsageError):
    """An attempt to create a publisher after manager has been initialized."""


class DuplicateEventError(EventManagerUsageError):
    """Two publishers were registered with the same name."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"{name}: you have already created an event with this "
            " name. Events must have unique names within this "
            " application."
        )


class KafkaTopicError(EventManagerUsageError):
    """A topic does not exist in Kafka, or we don't have access to it."""

    def __init__(self, topic: str) -> None:
        super().__init__(
            f"Topic: {topic} does not exist in Kafka, or we don't have the"
            " permissions to access it. See https://safir.lsst.io/metrics"
            " for how to provision Kafka topics, access, and other "
            " infrastructure for publishing metrics events."
        )
