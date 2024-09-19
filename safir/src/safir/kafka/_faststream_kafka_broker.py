"""Helpers for constructing an FastStream kafka broker."""

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
    KafkaSaslPlaintextSettings,
    KafkaSaslSslSettings,
    KafkaSslSettings,
)


def make_kafka_broker(
    config: KafkaConnectionSettings, client_id: str = "safir-faststream-broker"
) -> KafkaBroker:
    """Create a `FastStream Kafka broker <https://faststream.airt.ai/latest/kafka/#faststream-kafkabroker>`_.

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
            security = BaseSecurity(ssl_context=auth.ssl_context)
        case KafkaSaslSslSettings() | KafkaSaslPlaintextSettings():
            security = _sasl(auth)
        case KafkaPlaintextSettings():
            security = BaseSecurity()

    return KafkaBroker(
        bootstrap_servers=config.bootstrap_servers,
        client_id=client_id,
        security=security,
    )


def _sasl(
    config: KafkaSaslSslSettings | KafkaSaslPlaintextSettings,
) -> SASLScram512 | SASLScram256 | SASLPlaintext:
    """Create a FastStream Security for SASL authentication."""
    cls: type[SASLScram512 | SASLScram256 | SASLPlaintext]
    match config.sasl_mechanism:
        case KafkaSaslMechanism.SCRAM_SHA_512:
            cls = SASLScram512
        case KafkaSaslMechanism.SCRAM_SHA_256:
            cls = SASLScram256
        case KafkaSaslMechanism.PLAIN:
            cls = SASLPlaintext

    match config:
        case KafkaSaslSslSettings():
            ssl_context = config.ssl_context
        case KafkaSaslPlaintextSettings():
            ssl_context = None

    return cls(
        username=config.sasl_username,
        password=config.sasl_password.get_secret_value(),
        ssl_context=ssl_context,
    )
