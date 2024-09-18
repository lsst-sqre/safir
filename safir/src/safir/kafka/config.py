"""Kafka connection settings.

Adapted from Jonathan Sick's kafka work in `Ook <https://ook.lsst.io>`_.
"""

from __future__ import annotations

import ssl
from enum import StrEnum
from typing import Literal, Self

from aiokafka import helpers
from pydantic import BaseModel, Field, FilePath, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "KafkaConnectionSettings",
    "KafkaSecurityProtocol",
    "KafkaSaslMechanism",
    "KafkaConnectionSettings",
    "KafkaPlaintextSettings",
    "KafkaSslSettings",
]


class KafkaSecurityProtocol(StrEnum):
    """Kafka SASL security protocols."""

    SASL_PLAINTEXT = "SASL_PLAINTEXT"
    """Plain-text SASL-authenticated connection."""

    SASL_SSL = "SASL_SSL"
    """TLS-encrypted SASL-authenticated connection."""

    PLAINTEXT = "PLAINTEXT"
    """Plain-text connection."""

    SSL = "SSL"
    """SSL-encrypted SSL-authenticated connection."""


class KafkaSaslMechanism(StrEnum):
    """Kafka SASL mechanisms."""

    PLAIN = "PLAIN"
    """Plain-text SASL mechanism."""

    SCRAM_SHA_256 = "SCRAM-SHA-256"
    """SCRAM-SHA-256 SASL mechanism."""

    SCRAM_SHA_512 = "SCRAM-SHA-512"
    """SCRAM-SHA-512 SASL mechanism."""


class KafkaSslSettings(BaseModel):
    """Subset of settings required for SSL auth."""

    security_protocol: Literal[KafkaSecurityProtocol.SSL]

    cluster_ca_path: FilePath

    client_cert_path: FilePath

    client_key_path: FilePath

    @property
    def ssl_context(self) -> ssl.SSLContext:
        """An SSL context for connecting to Kafka, if the Kafka connection is
        configured to use TLS authentication.
        """
        return helpers.create_ssl_context(
            cafile=str(self.cluster_ca_path),
            certfile=str(self.client_cert_path),
            keyfile=str(self.client_key_path),
        )


class KafkaSaslSettings(BaseModel):
    """Subset of settings required for SASL auth."""

    security_protocol: Literal[
        KafkaSecurityProtocol.SASL_PLAINTEXT, KafkaSecurityProtocol.SASL_SSL
    ]

    sasl_mechanism: KafkaSaslMechanism

    sasl_username: str

    sasl_password: SecretStr

    cluster_ca_path: FilePath | None

    client_cert_path: FilePath | None

    client_key_path: FilePath | None

    @property
    def ssl_context(self) -> ssl.SSLContext:
        """An SSL context for connecting to Kafka, if the Kafka connection is
        configured to use TLS authentication.
        """
        cafile = None
        certfile = None
        keyfile = None

        if self.cluster_ca_path:
            cafile = str(self.cluster_ca_path)
        if self.client_cert_path:
            certfile = str(self.client_cert_path)
        if self.client_key_path:
            keyfile = str(self.client_key_path)
        return helpers.create_ssl_context(
            cafile=cafile,
            certfile=certfile,
            keyfile=keyfile,
        )


class KafkaPlaintextSettings(BaseModel):
    """Subset of settings required for Plaintext auth."""

    security_protocol: Literal[KafkaSecurityProtocol.PLAINTEXT]


class KafkaConnectionSettings(BaseSettings):
    """Settings for connecting to Kafka.

    This settings model supports different authentication methods, which each
    have different sets of required settings. All of these settings can be
    provided in ``KAFKA_`` prefixed environment variables. The
    ``auth_settings`` property enforces at runtime that the correct settings
    were provided for the desired authentication method, and provides
    non-optional attributes to access those settings::

    An instance of this model can be passed directly to the various client
    constructor functions in this module. This allows for succinct kafka setup
    in applications::

    .. code-block:: python

       from safir.kafka.config import KafkaConnectionSettings
       from safir.kafka import make_kafka_broker

       config = KafkaConnectionSettings()
       kafka_broker = make_kafka_broker(config)
    """

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
        title="Security Protocol",
        description=(
            "The authentication and encryption mode for the connection."
        ),
    )

    cluster_ca_path: FilePath | None = Field(
        default=None,
        title="Path to CA certificate file",
        description=(
            "The path to the CA certificate file to use for verifying the "
            "broker's certificate. "
            "This is only needed if the broker's certificate is not signed "
            "by a CA trusted by the operating system."
        ),
    )

    client_cert_path: FilePath | None = Field(
        default=None,
        title="Path to client certificate file",
        description=(
            "The path to the client certificate file to use for "
            "authentication. "
            "This is only needed if the broker is configured to require "
            "SSL client authentication."
        ),
    )

    client_key_path: FilePath | None = Field(
        default=None,
        title="Path to client key file",
        description=(
            "The path to the client key file to use for authentication. "
            "This is only needed if the broker is configured to require "
            "SSL client authentication."
        ),
    )

    sasl_mechanism: KafkaSaslMechanism | None = Field(
        default=None,
        title="SASL mechanism",
        description=(
            "The SASL mechanism to use for authentication. "
            "This is only needed if SASL authentication is enabled."
        ),
    )

    sasl_username: str | None = Field(
        default=None,
        title="SASL username",
        description=(
            "The username to use for SASL authentication. "
            "This is only needed if SASL authentication is enabled."
        ),
    )

    sasl_password: SecretStr | None = Field(
        default=None,
        title="SASL password",
        description=(
            "The password to use for SASL authentication. "
            "This is only needed if SASL authentication is enabled."
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="KAFKA_", case_sensitive=False
    )

    @model_validator(mode="after")
    def check_auth_settings(self) -> Self:
        """Validate that the correct parameters are specified for the correct
        auth method.
        """
        _ = self.auth_settings
        return self

    @property
    def auth_settings(
        self,
    ) -> KafkaSslSettings | KafkaSaslSettings | KafkaPlaintextSettings:
        """Return a model representing a paricular Kafka auth method.

        This method will fail with a ValidationError if an invalid set of
        settings were provided.
        """
        match self.security_protocol:
            case KafkaSecurityProtocol.PLAINTEXT:
                return KafkaPlaintextSettings(**self.model_dump())
            case (
                KafkaSecurityProtocol.SASL_SSL
                | KafkaSecurityProtocol.SASL_PLAINTEXT
            ):
                return KafkaSaslSettings(**self.model_dump())
            case KafkaSecurityProtocol.SSL:
                return KafkaSslSettings(**self.model_dump())
