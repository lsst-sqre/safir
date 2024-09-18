"""Helpers for constructing an aiokafka consumer."""

import ssl

from aiokafka import AIOKafkaConsumer

from .config import (
    KafkaConnectionSettings,
    KafkaPlaintextSettings,
    KafkaSaslSettings,
    KafkaSecurityProtocol,
    KafkaSslSettings,
)


def make_kafka_consumer(
    config: KafkaConnectionSettings,
    group_id: str | None = None,
    client_id: str = "safir-consumer",
) -> AIOKafkaConsumer:
    """Create an `aoikafka consumer <https://aiokafka.readthedocs.io/en/stable/consumer.html>`_.

    Parameters
    ----------
    client_id
        A name for this client. This string is passed in each request to
        servers and can be used to identify specific server-side log entries
        that correspond to this client.
    config
        Kafka connection and auth settings.
    """
    auth = config.auth_settings
    match auth:
        case KafkaSslSettings():
            return AIOKafkaConsumer(
                client_id=client_id,
                group_id=group_id,
                bootstrap_servers=config.bootstrap_servers,
                security_protocol="SSL",
                ssl_context=auth.ssl_context,
            )
        case KafkaSaslSettings():
            return _sasl(
                client_id=client_id,
                group_id=group_id,
                bootstrap_servers=config.bootstrap_servers,
                auth_config=auth,
            )
        case KafkaPlaintextSettings():
            return AIOKafkaConsumer(
                client_id=client_id,
                group_id=group_id,
                bootstrap_servers=config.bootstrap_servers,
                security_protocol="PLAINTEXT",
            )


def _sasl(
    client_id: str,
    bootstrap_servers: str,
    auth_config: KafkaSaslSettings,
    group_id: str | None = None,
) -> AIOKafkaConsumer:
    """Construct a consumer from SASL auth settings."""
    match auth_config.security_protocol:
        case KafkaSecurityProtocol.SASL_PLAINTEXT:
            ssl_context = None
        case KafkaSecurityProtocol.SASL_SSL:
            ssl_context = ssl.create_default_context()

    return AIOKafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        client_id=client_id,
        group_id=group_id,
        security_protocol=auth_config.security_protocol,
        sasl_mechanism=auth_config.sasl_mechanism,
        sasl_plain_username=auth_config.sasl_username,
        sasl_plain_password=auth_config.sasl_password.get_secret_value(),
        ssl_context=ssl_context,
    )
