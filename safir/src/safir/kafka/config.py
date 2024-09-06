"""Configuration for publishing events.

Cribbed from Jonathon's work in Ook:
https://github.com/lsst-sqre/ook/blob/main/src/ook/config.py
"""

import ssl
from enum import StrEnum
from pathlib import Path

from pydantic import AnyUrl, DirectoryPath, Field, FilePath, SecretStr
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


class SchemaRegistryConnectionSettings(BaseSettings):
    """Settings for connecting to a kafka schema registry."""

    url: AnyUrl = Field(
        ..., title="URL", description="URL for the schema registry"
    )


class KafkaConnectionSettings(BaseSettings):
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

    security_protocol: KafkaSecurityProtocol = Field(
        KafkaSecurityProtocol.PLAINTEXT,
        description="The security protocol to use when connecting to Kafka.",
    )

    cert_temp_dir: DirectoryPath | None = Field(
        None,
        description=(
            "Temporary writable directory for concatenating certificates."
        ),
    )

    cluster_ca_path: FilePath | None = Field(
        None,
        title="Path to CA certificate file",
        description=(
            "The path to the CA certificate file to use for verifying the "
            "broker's certificate. "
            "This is only needed if the broker's certificate is not signed "
            "by a CA trusted by the operating system."
        ),
    )

    client_ca_path: FilePath | None = Field(
        None,
        title="Path to client CA certificate file",
        description=(
            "The path to the client CA certificate file to use for "
            "authentication. "
            "This is only needed when the client certificate needs to be"
            "concatenated with the client CA certificate, which is common"
            "for Strimzi installations."
        ),
    )

    client_cert_path: FilePath | None = Field(
        None,
        title="Path to client certificate file",
        description=(
            "The path to the client certificate file to use for "
            "authentication. "
            "This is only needed if the broker is configured to require "
            "SSL client authentication."
        ),
    )

    client_key_path: FilePath | None = Field(
        None,
        title="Path to client key file",
        description=(
            "The path to the client key file to use for authentication. "
            "This is only needed if the broker is configured to require "
            "SSL client authentication."
        ),
    )

    client_key_password: SecretStr | None = Field(
        None,
        title="Password for client key file",
        description=(
            "The password to use for decrypting the client key file. "
            "This is only needed if the client key file is encrypted."
        ),
    )

    sasl_mechanism: KafkaSaslMechanism | None = Field(
        KafkaSaslMechanism.PLAIN,
        title="SASL mechanism",
        description=(
            "The SASL mechanism to use for authentication. "
            "This is only needed if SASL authentication is enabled."
        ),
    )

    sasl_username: str | None = Field(
        None,
        title="SASL username",
        description=(
            "The username to use for SASL authentication. "
            "This is only needed if SASL authentication is enabled."
        ),
    )

    sasl_password: SecretStr | None = Field(
        None,
        title="SASL password",
        description=(
            "The password to use for SASL authentication. "
            "This is only needed if SASL authentication is enabled."
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="KAFKA_", case_sensitive=False
    )

    @property
    def ssl_context(self) -> ssl.SSLContext | None:
        """An SSL context for connecting to Kafka with aiokafka, if the
        Kafka connection is configured to use SSL.
        """
        if (
            self.security_protocol != KafkaSecurityProtocol.SSL
            or self.cluster_ca_path is None
            or self.client_cert_path is None
            or self.client_key_path is None
        ):
            return None

        client_cert_path = Path(self.client_cert_path)

        if self.client_ca_path is not None:
            # Need to contatenate the client cert and CA certificates. This is
            # typical for Strimzi-based Kafka clusters.
            if self.cert_temp_dir is None:
                raise RuntimeError(
                    "KAFKIT_KAFKA_CERT_TEMP_DIR must be set when "
                    "a client CA certificate is provided."
                )
            client_ca = Path(self.client_ca_path).read_text()
            client_cert = Path(self.client_cert_path).read_text()
            sep = "" if client_ca.endswith("\n") else "\n"
            new_client_cert = sep.join([client_cert, client_ca])
            new_client_cert_path = Path(self.cert_temp_dir) / "client.crt"
            new_client_cert_path.write_text(new_client_cert)
            client_cert_path = Path(new_client_cert_path)

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
