"""Helpers for constructing an aiokafka consumer."""

from aiokafka import AIOKafkaConsumer

from ..config import (
    KafkaConnectionSettings,
    KafkaPlaintextSettings,
    KafkaSaslPlaintextSettings,
    KafkaSaslSslSettings,
    KafkaSslSettings,
)

__all__ = ["make_kafka_consumer"]


def make_kafka_consumer(
    config: KafkaConnectionSettings,
    group_id: str | None = None,
    client_id: str = "safir-consumer",
) -> AIOKafkaConsumer:
    """Create an `aoikafka consumer <https://aiokafka.readthedocs.io/en/stable/consumer.html>`_.

    Parameters
    ----------
    config
        Kafka connection and auth settings.
    group_id
        name of the consumer group to join for dynamic partition assignment (if
        enabled), and to use for fetching and committing offsets. If None,
        auto-partition assignment (via group coordinator) and offset commits
        are disabled.
    client_id
        A name for this client. This string is passed in each request to
        servers and can be used to identify specific server-side log entries
        that correspond to this client.
    """
    validated = config.validated
    match validated:
        case KafkaSslSettings():
            return AIOKafkaConsumer(
                client_id=client_id,
                group_id=group_id,
                bootstrap_servers=validated.bootstrap_servers,
                security_protocol="SSL",
                ssl_context=validated.ssl_context,
            )
        case KafkaSaslSslSettings() | KafkaSaslPlaintextSettings():
            return _sasl(
                client_id=client_id,
                group_id=group_id,
                config=validated,
            )
        case KafkaPlaintextSettings():
            return AIOKafkaConsumer(
                client_id=client_id,
                group_id=group_id,
                bootstrap_servers=validated.bootstrap_servers,
                security_protocol="PLAINTEXT",
            )


def _sasl(
    client_id: str,
    config: KafkaSaslSslSettings | KafkaSaslPlaintextSettings,
    group_id: str | None = None,
) -> AIOKafkaConsumer:
    """Construct a consumer from SASL auth settings."""
    match config:
        case KafkaSaslSslSettings():
            ssl_context = config.ssl_context
        case KafkaSaslPlaintextSettings():
            ssl_context = None

    return AIOKafkaConsumer(
        bootstrap_servers=config.bootstrap_servers,
        client_id=client_id,
        group_id=group_id,
        security_protocol=config.security_protocol,
        sasl_mechanism=config.sasl_mechanism,
        sasl_plain_username=config.sasl_username,
        sasl_plain_password=config.sasl_password.get_secret_value(),
        ssl_context=ssl_context,
    )
