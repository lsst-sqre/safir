"""Helpers for constructing an aiokafka admin client."""

from aiokafka.admin.client import AIOKafkaAdminClient

from ..config import (
    KafkaConnectionSettings,
    KafkaPlaintextSettings,
    KafkaSaslPlaintextSettings,
    KafkaSaslSslSettings,
    KafkaSslSettings,
)

__all__ = ["make_kafka_admin_client"]


def make_kafka_admin_client(
    config: KafkaConnectionSettings, client_id: str = "safir-admin-client"
) -> AIOKafkaAdminClient:
    """Create an `aiokafka admin client <https://github.com/aio-libs/aiokafka/blob/master/aiokafka/admin/client.py>`_.

    Parameters
    ----------
    config
        Kafka connection and auth settings.
    client_id
        A name for this client. This string is passed in each request to
        servers and can be used to identify specific server-side log entries
        that correspond to this client.
    """
    validated = config.validated
    match validated:
        case KafkaSslSettings():
            return AIOKafkaAdminClient(
                client_id=client_id,
                bootstrap_servers=validated.bootstrap_servers,
                security_protocol="SSL",
                ssl_context=validated.ssl_context,
            )
        case KafkaSaslSslSettings() | KafkaSaslPlaintextSettings():
            return _sasl(
                client_id=client_id,
                config=validated,
            )
        case KafkaPlaintextSettings():
            return AIOKafkaAdminClient(
                client_id=client_id,
                bootstrap_servers=validated.bootstrap_servers,
                security_protocol="PLAINTEXT",
            )


def _sasl(
    client_id: str,
    config: KafkaSaslSslSettings | KafkaSaslPlaintextSettings,
) -> AIOKafkaAdminClient:
    """Construct an admin client from SASL auth settings."""
    match config:
        case KafkaSaslPlaintextSettings():
            ssl_context = None
        case KafkaSaslSslSettings():
            ssl_context = config.ssl_context

    return AIOKafkaAdminClient(
        bootstrap_servers=config.bootstrap_servers,
        client_id=client_id,
        security_protocol=config.security_protocol,
        sasl_mechanism=config.sasl_mechanism,
        sasl_plain_username=config.sasl_username,
        sasl_plain_password=config.sasl_password.get_secret_value(),
        ssl_context=ssl_context,
    )
