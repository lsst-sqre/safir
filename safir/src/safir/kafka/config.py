"""Configuration for publishing events.

Cribbed from Jonathon's work in Ook:
https://github.com/lsst-sqre/ook/blob/main/src/ook/config.py
"""

import ssl
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias

from pydantic import DirectoryPath, Field, FilePath, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSecurityProtocol(StrEnum):
    """Kafka security protocols understood by aiokafka."""

    PLAINTEXT = "PLAINTEXT"
    """Plain-text connection."""

    SSL = "SSL"
    """TLS-encrypted connection."""


class KafkaSaslMechanism(StrEnum):
    """Kafka SASL mechanisms understood by aiokafka."""

    PLAIN = "PLAIN"
    """Plain-text SASL mechanism."""

    SCRAM_SHA_256 = "SCRAM-SHA-256"
    """SCRAM-SHA-256 SASL mechanism."""

    SCRAM_SHA_512 = "SCRAM-SHA-512"
    """SCRAM-SHA-512 SASL mechanism."""


class KafkaBaseConnectionSettings(BaseSettings):
    """Settings for connecting to Kafka."""

    bootstrap_servers: str = Field(
        ...,
        title="Kafka bootstrap servers",
        description=(
            "A comma-separated list of Kafka brokers to connect to. "
            "This should be a list of hostnames or IP addresses, "
            "each optionally followed by a port number, separated by "
            "commas. "
            "For example: ``kafka-1:9092,kafka-2:9092,kafka-3:9092``."
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="KAFKA_", case_sensitive=False
    )


class KafkaSaslConnectionSettings(KafkaBaseConnectionSettings):
    """Settings for connecting to a kafka cluster via SASL."""

    security_protocol: KafkaSecurityProtocol = Field(
        KafkaSecurityProtocol.PLAINTEXT,
        description="The security protocol to use when connecting to Kafka.",
    )

    sasl_mechanism: KafkaSaslMechanism = Field(
        KafkaSaslMechanism.PLAIN,
        title="SASL mechanism",
        description=("The SASL mechanism to use for authentication. "),
    )

    sasl_username: str = Field(
        title="SASL username",
        description=("The username to use for SASL authentication. "),
    )

    sasl_password: SecretStr = Field(
        title="SASL password",
        description=("The password to use for SASL authentication. "),
    )


class KafkaTlsConnectionSettings(KafkaBaseConnectionSettings):
    """Settings for connecting to a kafka cluster via TLS."""

    cert_temp_dir: DirectoryPath = Field(
        description=(
            "Temporary writable directory for concatenating certificates."
        ),
    )

    cluster_ca_path: FilePath = Field(
        title="Path to CA certificate file",
        description=(
            "The path to the CA certificate file to use for verifying the "
            "broker's certificate. "
            "This is only needed if the broker's certificate is not signed "
            "by a CA trusted by the operating system."
        ),
    )

    client_cert_path: FilePath = Field(
        title="Path to client certificate file",
        description=(
            "The path to the client certificate file to use for "
            "authentication. "
            "This is only needed if the broker is configured to require "
            "SSL client authentication."
        ),
    )

    client_key_path: FilePath = Field(
        title="Path to client key file",
        description=(
            "The path to the client key file to use for authentication. "
            "This is only needed if the broker is configured to require "
            "SSL client authentication."
        ),
    )

    @property
    def ssl_context(self) -> ssl.SSLContext | None:
        """An SSL context for connecting to Kafka with aiokafka, if the
        Kafka connection is configured to use SSL.
        """
        client_cert_path = Path(self.client_cert_path)

        # Create an SSL context on the basis that we're the client
        # authenticating the server (the Kafka broker).
        ssl_context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH, cafile=str(self.cluster_ca_path)
        )
        # Add the certificates that the Kafka broker uses to authenticate us.
        ssl_context.load_cert_chain(
            certfile=str(client_cert_path), keyfile=str(self.client_key_path)
        )

        return ssl_context


KafkaConnectionSettings: TypeAlias = (
    KafkaSaslConnectionSettings | KafkaTlsConnectionSettings
)
