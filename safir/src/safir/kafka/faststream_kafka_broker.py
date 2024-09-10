import ssl

from faststream.kafka import KafkaBroker
from faststream.security import BaseSecurity, SASLPlaintext, SASLScram512

from .config import (
    KafkaConnectionSettings,
    KafkaSaslConnectionSettings,
    KafkaSaslMechanism,
    KafkaTlsConnectionSettings,
)


def make_kafka_broker(
    config: KafkaConnectionSettings, client_id: str
) -> KafkaBroker:
    """Create a FastStream Kafka broker."""
    match config:
        case KafkaSaslConnectionSettings():
            return _sasl(config, client_id)
        case KafkaTlsConnectionSettings():
            return _tls(config, client_id)


def _sasl(config: KafkaSaslConnectionSettings, client_id: str) -> KafkaBroker:
    match config.sasl_mechanism:
        case KafkaSaslMechanism.SCRAM_SHA_512:
            cls = SASLScram512
        case KafkaSaslMechanism.SCRAM_SHA_256:
            cls = SASLScram512
        case KafkaSaslMechanism.PLAIN:
            cls = SASLPlaintext

    return KafkaBroker(
        bootstrap_servers=config.bootstrap_servers,
        client_id=client_id,
        security=cls(
            username=config.sasl_username,
            password=config.sasl_password.get_secret_value(),
            ssl_context=ssl.create_default_context(),
        ),
    )


def _tls(config: KafkaTlsConnectionSettings, client_id: str) -> KafkaBroker:
    return KafkaBroker(
        bootstrap_servers=config.bootstrap_servers,
        client_id=client_id,
        security=BaseSecurity(ssl_context=config.ssl_context),
    )
