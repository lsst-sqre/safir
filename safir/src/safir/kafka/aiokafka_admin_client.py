import ssl

from aiokafka.admin.client import AIOKafkaAdminClient

from .config import (
    KafkaConnectionSettings,
    KafkaSaslSettings,
    KafkaSecurityProtocol,
    KafkaTlsSettings,
)


def make_kafka_admin_client(
    config: KafkaConnectionSettings, client_id: str
) -> AIOKafkaAdminClient:
    """Create a FastStream Kafka broker."""
    auth = config.auth_settings
    match auth:
        case KafkaTlsSettings():
            return _tls(
                client_id=client_id,
                bootstrap_servers=config.bootstrap_servers,
                auth_config=auth,
            )
        case KafkaSaslSettings():
            return _sasl(
                client_id=client_id,
                bootstrap_servers=config.bootstrap_servers,
                auth_config=auth,
            )


def _tls(
    client_id: str, bootstrap_servers: str, auth_config: KafkaTlsSettings
) -> AIOKafkaAdminClient:
    return AIOKafkaAdminClient(
        bootstrap_servers=bootstrap_servers,
        client_id=client_id,
        security_protocol="SSL",
        ssl_context=auth_config.ssl_context,
    )


def _sasl(
    client_id: str, bootstrap_servers: str, auth_config: KafkaSaslSettings
) -> AIOKafkaAdminClient:
    match auth_config.security_protocol:
        case KafkaSecurityProtocol.SASL_PLAINTEXT:
            ssl_context = None
        case KafkaSecurityProtocol.SASL_SSL:
            ssl_context = ssl.create_default_context()

    return AIOKafkaAdminClient(
        bootstrap_servers=bootstrap_servers,
        client_id=client_id,
        security_protocol=auth_config.security_protocol,
        sasl_mechanism=auth_config.sasl_mechanism,
        sasl_plain_username=auth_config.sasl_username,
        sasl_plain_password=auth_config.sasl_password.get_secret_value(),
        ssl_context=ssl_context,
    )
