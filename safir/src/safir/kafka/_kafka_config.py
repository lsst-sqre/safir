"""Kafka connection settings.

Adapted from Jonathan Sick's kafka work in `Ook <https://ook.lsst.io>`_.
"""

from __future__ import annotations

import ssl
from enum import StrEnum
from typing import Literal, NotRequired, Self, TypedDict

from aiokafka import helpers
from faststream.security import (
    BaseSecurity,
    SASLPlaintext,
    SASLScram256,
    SASLScram512,
)
from pydantic import BaseModel, Field, FilePath, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "AIOKafkaParams",
    "FastStreamBrokerParams",
    "KafkaConnectionSettings",
    "KafkaPlaintextSettings",
    "KafkaPlaintextSettings",
    "KafkaSaslMechanism",
    "KafkaSaslPlaintextSettings",
    "KafkaSaslSslSettings",
    "KafkaSecurityProtocol",
    "KafkaSslSettings",
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


class FastStreamBrokerParams(TypedDict):
    bootstrap_servers: str
    security: BaseSecurity


class AIOKafkaParams(TypedDict):
    bootstrap_servers: str
    security_protocol: str
    sasl_mechanism: NotRequired[str]
    sasl_plain_username: NotRequired[str]
    sasl_plain_password: NotRequired[str]
    ssl_context: NotRequired[ssl.SSLContext]


class KafkaSslSettings(BaseModel):
    """Subset of settings required for SSL auth."""

    bootstrap_servers: str

    security_protocol: Literal[KafkaSecurityProtocol.SSL]

    cluster_ca_path: FilePath

    client_cert_path: FilePath

    client_key_path: FilePath

    @property
    def ssl_context(self) -> ssl.SSLContext:
        """An SSL context for connecting to Kafka."""
        return helpers.create_ssl_context(
            cafile=str(self.cluster_ca_path),
            certfile=str(self.client_cert_path),
            keyfile=str(self.client_key_path),
        )

    @property
    def faststream_params(self) -> FastStreamBrokerParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security": BaseSecurity(ssl_context=self.ssl_context),
        }

    @property
    def aiokafka_params(self) -> AIOKafkaParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security_protocol": self.security_protocol,
            "ssl_context": self.ssl_context,
        }


class KafkaSaslPlaintextSettings(BaseModel):
    """Subset of settings required for SASL SSLauth."""

    bootstrap_servers: str

    security_protocol: Literal[
        KafkaSecurityProtocol.SASL_PLAINTEXT, KafkaSecurityProtocol.SASL_SSL
    ]

    sasl_mechanism: KafkaSaslMechanism = KafkaSaslMechanism.SCRAM_SHA_512

    sasl_username: str

    sasl_password: SecretStr

    @property
    def faststream_params(self) -> FastStreamBrokerParams:
        cls: type[SASLScram512 | SASLScram256 | SASLPlaintext]
        match self.sasl_mechanism:
            case KafkaSaslMechanism.SCRAM_SHA_512:
                cls = SASLScram512
            case KafkaSaslMechanism.SCRAM_SHA_256:
                cls = SASLScram256
            case KafkaSaslMechanism.PLAIN:
                cls = SASLPlaintext

        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security": cls(
                username=self.sasl_username,
                password=self.sasl_password.get_secret_value(),
            ),
        }

    @property
    def aiokafka_params(self) -> AIOKafkaParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security_protocol": self.security_protocol,
            "sasl_mechanism": self.sasl_mechanism,
            "sasl_plain_username": self.sasl_username,
            "sasl_plain_password": self.sasl_password.get_secret_value(),
        }


class KafkaSaslSslSettings(BaseModel):
    """Subset of settings required for SASL PLAINTEXT auth."""

    bootstrap_servers: str

    security_protocol: Literal[
        KafkaSecurityProtocol.SASL_PLAINTEXT, KafkaSecurityProtocol.SASL_SSL
    ]

    sasl_mechanism: KafkaSaslMechanism = KafkaSaslMechanism.SCRAM_SHA_512

    sasl_username: str

    sasl_password: SecretStr

    cluster_ca_path: FilePath | None

    @property
    def ssl_context(self) -> ssl.SSLContext:
        """An SSL context for connecting to Kafka."""
        cafile = None

        if self.cluster_ca_path:
            cafile = str(self.cluster_ca_path)
        return helpers.create_ssl_context(
            cafile=cafile,
        )

    @property
    def faststream_params(self) -> FastStreamBrokerParams:
        cls: type[SASLScram512 | SASLScram256 | SASLPlaintext]
        match self.sasl_mechanism:
            case KafkaSaslMechanism.SCRAM_SHA_512:
                cls = SASLScram512
            case KafkaSaslMechanism.SCRAM_SHA_256:
                cls = SASLScram256
            case KafkaSaslMechanism.PLAIN:
                cls = SASLPlaintext

        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security": cls(
                username=self.sasl_username,
                password=self.sasl_password.get_secret_value(),
                ssl_context=self.ssl_context,
            ),
        }

    @property
    def aiokafka_params(self) -> AIOKafkaParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security_protocol": self.security_protocol,
            "ssl_context": self.ssl_context,
            "sasl_mechanism": self.sasl_mechanism,
            "sasl_plain_username": self.sasl_username,
            "sasl_plain_password": self.sasl_password.get_secret_value(),
        }


class KafkaPlaintextSettings(BaseModel):
    """Subset of settings required for Plaintext auth."""

    bootstrap_servers: str

    security_protocol: Literal[KafkaSecurityProtocol.PLAINTEXT]

    @property
    def faststream_params(self) -> FastStreamBrokerParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security": BaseSecurity(),
        }

    @property
    def aiokafka_params(self) -> AIOKafkaParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security_protocol": self.security_protocol,
        }


class KafkaConnectionSettings(BaseSettings):
    """Settings for connecting to Kafka.

    This settings model supports different authentication methods, which each
    have different sets of required settings. All of these settings can be
    provided in ``KAFKA_`` prefixed environment variables. Instances of this
    model have properties that can be used to construct different types of
    kafka clients:

    .. code-block:: python

       from faststream.broker import KafkaBroker

       from safir.kafka import KafkaConnectionSettings


       config = KafkaConnectionSettings()
       kafka_broker = KafkaBroker(**config.faststream_broker_params)

    When using this model directly, The ``validated`` property enforces at
    runtime that the correct settings were provided for the desired
    authentication method, and returns models to access those settings in a
    type-safe way:

    .. code-block:: python

       from pathlib import Path


       # ValidationError at runtime: ``client_key_path`` is not provided
       config = KafkaConnectionSettings(
           bootstrap_servers="something:1234",
           security_protocol=KafkaSecurityProtocol.SSL,
           cluster_ca_path=Path("/some/cert.crt"),
           client_cert_path=Path("/some/other/cert.crt"),
       )

       config = KafkaConnectionSettings(
           bootstrap_servers="something:1234",
           security_protocol=KafkaSecurityProtocol.SSL,
           cluster_ca_path=Path("/some/path/ca.crt"),
           client_cert_path=Path("/some/path/user.crt"),
           client_key_path=Path("/some/path/user.key"),
       )

       blah = config.validated.sasl_username  # Static type error
    """

    bootstrap_servers: str = Field(
        ...,
        title="Kafka bootstrap servers",
        description=(
            "A comma-separated list of Kafka brokers to connect to. "
            "This should be a list of hostnames or IP addresses, "
            "each optionally followed by a port number, separated by "
            "commas. "
        ),
        examples=["kafka-1:9092,kafka-2:9092,kafka-3:9092", "kafka:9092"],
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
            "The path to the PEM-formatted CA certificate file to use for "
            "verifying the broker's certificate. "
            "This is only needed for SSL and SASL_SSL security protocols, and"
            "even in those cases, only when the broker's certificate is not "
            "signed by a CA trusted by the operating system."
        ),
        examples=["/some/dir/ca.crt"],
    )

    client_cert_path: FilePath | None = Field(
        default=None,
        title="Path to client certificate file",
        description=(
            "The path to the PEM-formated client certificate file to use for "
            "authentication. "
            "This is only needed if the broker is configured to require "
            "SSL client authentication."
        ),
        examples=["/some/dir/user.crt"],
    )

    client_key_path: FilePath | None = Field(
        default=None,
        title="Path to client key file",
        description=(
            "The path to the PEM-formatted client key file to use for "
            "authentication. This is only needed if for the SSL security"
            "protocol."
        ),
        examples=["/some/dir/user.key"],
    )

    sasl_mechanism: KafkaSaslMechanism | None = Field(
        default=None,
        title="SASL mechanism",
        description=(
            "The SASL mechanism to use for authentication. "
            "This is only needed for the SASL_SSL and SASL_PLAINTEXT security"
            "protocols."
        ),
    )

    sasl_username: str | None = Field(
        default=None,
        title="SASL username",
        description=(
            "The username to use for SASL authentication. "
            "This is only needed for the SASL_SSL and SASL_PLAINTEXT security"
            "protocols."
        ),
    )

    sasl_password: SecretStr | None = Field(
        default=None,
        title="SASL password",
        description=(
            "The password to use for SASL authentication. "
            "This is only needed for the SASL_SSL and SASL_PLAINTEXT security"
            "protocols."
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="KAFKA_", case_sensitive=False
    )

    @model_validator(mode="after")
    def validate_auth_settings(self) -> Self:
        """Validate that the correct combination of parameters is specified."""
        _ = self.validated
        return self

    @property
    def validated(
        self,
    ) -> (
        KafkaSslSettings
        | KafkaSaslSslSettings
        | KafkaSaslPlaintextSettings
        | KafkaPlaintextSettings
    ):
        """Return a model with a subset of settings for a Kafka auth method.

        This method will fail with a ValidationError if an invalid set of
        settings were provided.
        """
        match self.security_protocol:
            case KafkaSecurityProtocol.PLAINTEXT:
                return KafkaPlaintextSettings(**self.model_dump())
            case KafkaSecurityProtocol.SASL_SSL:
                return KafkaSaslSslSettings(**self.model_dump())
            case KafkaSecurityProtocol.SASL_PLAINTEXT:
                return KafkaSaslPlaintextSettings(**self.model_dump())
            case KafkaSecurityProtocol.SSL:
                return KafkaSslSettings(**self.model_dump())

    @property
    def faststream_params(self) -> FastStreamBrokerParams:
        return self.validated.faststream_params

    @property
    def aiokafka_params(self) -> AIOKafkaParams:
        return self.validated.aiokafka_params
