import ssl

from faststream.kafka import KafkaBroker
from faststream.security import (
    BaseSecurity,
    SASLPlaintext,
    SASLScram256,
    SASLScram512,
)

from .config import (
    KafkaConnectionSettings,
    KafkaPlaintextSettings,
    KafkaSaslMechanism,
    KafkaSaslSettings,
    KafkaTlsSettings,
)


def make_kafka_broker(
    config: KafkaConnectionSettings, client_id: str
) -> KafkaBroker:
    """Create a FastStream Kafka broker."""
    auth = config.auth_settings
    match auth:
        case KafkaTlsSettings():
            security = BaseSecurity(ssl_context=auth.ssl_context)
        case KafkaSaslSettings():
            security = _sasl(auth)
        case KafkaPlaintextSettings():
            security = BaseSecurity()

    return KafkaBroker(
        bootstrap_servers=config.bootstrap_servers,
        client_id=client_id,
        security=security,
    )


def _sasl(
    config: KafkaSaslSettings,
) -> SASLScram512 | SASLScram256 | SASLPlaintext:
    """Create a Faststream Security for SASL authentication."""
    cls: type[SASLScram512 | SASLScram256 | SASLPlaintext]
    match config.sasl_mechanism:
        case KafkaSaslMechanism.SCRAM_SHA_512:
            cls = SASLScram512
        case KafkaSaslMechanism.SCRAM_SHA_256:
            cls = SASLScram256
        case KafkaSaslMechanism.PLAIN:
            cls = SASLPlaintext

    return cls(
        username=config.sasl_username,
        password=config.sasl_password.get_secret_value(),
        ssl_context=ssl.create_default_context(),
    )
