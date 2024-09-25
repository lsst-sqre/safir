"""Metrics exceptions."""

__all__ = [
    "CreateAfterRegisterError",
    "DuplicateEventError",
    "KafkaTopicError",
]


class CreateAfterRegisterError(Exception):
    """An attempt to create a publisher after manager has been initialized."""


class DuplicateEventError(Exception):
    """Two publishers were registered with the same name."""

    def __init__(self, name: str) -> None:
        self.message = (
            f"{name}: you have already created an event with this "
            " name. Events must have unique names within this "
            " application."
        )
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class KafkaTopicError(Exception):
    """A topic does not exist in Kafka, or we don't have access to it."""

    def __init__(self, topic: str) -> None:
        self.message = (
            f"Topic: {topic} does not exist in Kafka, or we don't have the"
            " permissions to access it. See https://safir.lsst.io/metrics"
            " for how to provision Kafka topics, access, and other "
            " infrastructure for publishing metrics events."
        )
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message
