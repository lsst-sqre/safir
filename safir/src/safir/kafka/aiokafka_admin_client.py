import ssl

from aiokafka.admin.client import AIOKafkaAdminClient

from .config import (
    KafkaConnectionSettings,
    KafkaSaslConnectionSettings,
    KafkaSecurityProtocol,
    KafkaTlsConnectionSettings,
)


def make_kafka_admin_client(
    config: KafkaConnectionSettings, client_id: str
) -> AIOKafkaAdminClient:
    """Create a FastStream Kafka broker."""
    match config:
        case KafkaSaslConnectionSettings():
            return _sasl(config, client_id)
        case KafkaTlsConnectionSettings():
            return _tls(config, client_id)


def _sasl(
    config: KafkaSaslConnectionSettings, client_id: str
) -> AIOKafkaAdminClient:
    match config.security_protocol:
        case KafkaSecurityProtocol.PLAINTEXT:
            protocol = "SASL_PLAINTEXT"
            ssl_context = None
        case KafkaSecurityProtocol.SSL:
            protocol = "SASL_SSL"
            ssl_context = ssl.create_default_context()

    return AIOKafkaAdminClient(
        bootstrap_servers=config.bootstrap_servers,
        client_id=client_id,
        security_protocol=protocol,
        sasl_mechanism=config.sasl_mechanism,
        sasl_plain_username=config.sasl_username,
        sasl_plain_password=config.sasl_password.get_secret_value(),
        ssl_context=ssl_context,
    )


def _tls(
    config: KafkaTlsConnectionSettings, client_id: str
) -> AIOKafkaAdminClient:
    return AIOKafkaAdminClient(
        bootstrap_servers=config.bootstrap_servers,
        client_id=client_id,
        security_protocol="SSL",
        ssl_context=ssl.create_default_context(),
    )
