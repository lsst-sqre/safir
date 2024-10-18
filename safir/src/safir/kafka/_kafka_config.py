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
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    FilePath,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "AIOKafkaParams",
    "FastStreamBrokerParams",
    "KafkaConnectionSettings",
    "PlaintextSettings",
    "PlaintextSettings",
    "SaslMechanism",
    "SaslPlaintextSettings",
    "SaslSslSettings",
    "SecurityProtocol",
    "SslSettings",
    "SslSettings",
]


class SecurityProtocol(StrEnum):
    """Kafka SASL security protocols."""

    SASL_PLAINTEXT = "SASL_PLAINTEXT"
    """Plain-text SASL-authenticated connection."""

    SASL_SSL = "SASL_SSL"
    """TLS-encrypted SASL-authenticated connection."""

    PLAINTEXT = "PLAINTEXT"
    """Plain-text connection."""

    SSL = "SSL"
    """SSL-encrypted SSL-authenticated connection."""


class SaslMechanism(StrEnum):
    """Kafka SASL mechanisms."""

    PLAIN = "PLAIN"
    """Plain-text SASL mechanism."""

    SCRAM_SHA_256 = "SCRAM-SHA-256"
    """SCRAM-SHA-256 SASL mechanism."""

    SCRAM_SHA_512 = "SCRAM-SHA-512"
    """SCRAM-SHA-512 SASL mechanism."""


class FastStreamBrokerParams(TypedDict):
    """Type for parameters to the constructor of a FastStream broker."""

    bootstrap_servers: str
    security: BaseSecurity


class AIOKafkaParams(TypedDict):
    """Type for parameters to the constructor of an aiokafka client."""

    bootstrap_servers: str
    security_protocol: str
    sasl_mechanism: NotRequired[str]
    sasl_plain_username: NotRequired[str]
    sasl_plain_password: NotRequired[str]
    ssl_context: NotRequired[ssl.SSLContext]


class SslSettings(BaseModel):
    """Subset of settings required for SSL auth."""

    bootstrap_servers: str

    security_protocol: Literal[SecurityProtocol.SSL]

    cluster_ca_path: FilePath

    client_cert_path: FilePath

    client_key_path: FilePath

    def to_ssl_context(self) -> ssl.SSLContext:
        """Create an SSL context for connecting to Kafka."""
        return helpers.create_ssl_context(
            cafile=str(self.cluster_ca_path),
            certfile=str(self.client_cert_path),
            keyfile=str(self.client_key_path),
        )

    def to_faststream_params(self) -> FastStreamBrokerParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security": BaseSecurity(ssl_context=self.to_ssl_context()),
        }

    def to_aiokafka_params(self) -> AIOKafkaParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security_protocol": self.security_protocol,
            "ssl_context": self.to_ssl_context(),
        }


class SaslPlaintextSettings(BaseModel):
    """Subset of settings required for SASL SSLauth."""

    bootstrap_servers: str

    security_protocol: Literal[
        SecurityProtocol.SASL_PLAINTEXT, SecurityProtocol.SASL_SSL
    ]

    sasl_mechanism: SaslMechanism = SaslMechanism.SCRAM_SHA_512

    sasl_username: str

    sasl_password: SecretStr

    def to_faststream_params(self) -> FastStreamBrokerParams:
        cls: type[SASLScram512 | SASLScram256 | SASLPlaintext]
        match self.sasl_mechanism:
            case SaslMechanism.SCRAM_SHA_512:
                cls = SASLScram512
            case SaslMechanism.SCRAM_SHA_256:
                cls = SASLScram256
            case SaslMechanism.PLAIN:
                cls = SASLPlaintext

        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security": cls(
                username=self.sasl_username,
                password=self.sasl_password.get_secret_value(),
            ),
        }

    def to_aiokafka_params(self) -> AIOKafkaParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security_protocol": self.security_protocol,
            "sasl_mechanism": self.sasl_mechanism,
            "sasl_plain_username": self.sasl_username,
            "sasl_plain_password": self.sasl_password.get_secret_value(),
        }


class SaslSslSettings(BaseModel):
    """Subset of settings required for SASL PLAINTEXT auth."""

    bootstrap_servers: str

    security_protocol: Literal[
        SecurityProtocol.SASL_PLAINTEXT, SecurityProtocol.SASL_SSL
    ]

    sasl_mechanism: SaslMechanism = SaslMechanism.SCRAM_SHA_512

    sasl_username: str

    sasl_password: SecretStr

    cluster_ca_path: FilePath | None

    def to_ssl_context(self) -> ssl.SSLContext:
        """Make an SSL context for connecting to Kafka."""
        cafile = None

        if self.cluster_ca_path:
            cafile = str(self.cluster_ca_path)
        return helpers.create_ssl_context(
            cafile=cafile,
        )

    def to_faststream_params(self) -> FastStreamBrokerParams:
        cls: type[SASLScram512 | SASLScram256 | SASLPlaintext]
        match self.sasl_mechanism:
            case SaslMechanism.SCRAM_SHA_512:
                cls = SASLScram512
            case SaslMechanism.SCRAM_SHA_256:
                cls = SASLScram256
            case SaslMechanism.PLAIN:
                cls = SASLPlaintext

        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security": cls(
                username=self.sasl_username,
                password=self.sasl_password.get_secret_value(),
                ssl_context=self.to_ssl_context(),
            ),
        }

    def to_aiokafka_params(self) -> AIOKafkaParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security_protocol": self.security_protocol,
            "ssl_context": self.to_ssl_context(),
            "sasl_mechanism": self.sasl_mechanism,
            "sasl_plain_username": self.sasl_username,
            "sasl_plain_password": self.sasl_password.get_secret_value(),
        }


class PlaintextSettings(BaseModel):
    """Subset of settings required for Plaintext auth."""

    bootstrap_servers: str

    security_protocol: Literal[SecurityProtocol.PLAINTEXT]

    def to_faststream_params(self) -> FastStreamBrokerParams:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "security": BaseSecurity(),
        }

    def to_aiokafka_params(self) -> AIOKafkaParams:
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
        title="Kafka bootstrap servers",
        description=(
            "A comma-separated list of Kafka brokers to connect to. "
            "This should be a list of hostnames or IP addresses, "
            "each optionally followed by a port number, separated by "
            "commas."
        ),
        examples=["kafka-1:9092,kafka-2:9092,kafka-3:9092", "kafka:9092"],
        validation_alias=AliasChoices(
            "bootstrapServers", "KAFKA_BOOTSTRAP_SERVERS"
        ),
    )

    security_protocol: SecurityProtocol = Field(
        title="Security Protocol",
        description=(
            "The authentication and encryption mode for the connection."
        ),
        validation_alias=AliasChoices(
            "securityProtocol", "KAFKA_SECURITY_PROTOCOL"
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
        validation_alias=AliasChoices(
            "clusterCaPath", "KAFKA_CLUSTER_CA_PATH"
        ),
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
        validation_alias=AliasChoices(
            "clientCertPath", "KAFKA_CLIENT_CERT_PATH"
        ),
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
        validation_alias=AliasChoices(
            "clientKeyPath", "KAFKA_CLIENT_KEY_PATH"
        ),
    )

    sasl_mechanism: SaslMechanism | None = Field(
        default=None,
        title="SASL mechanism",
        description=(
            "The SASL mechanism to use for authentication. "
            "This is only needed for the SASL_SSL and SASL_PLAINTEXT security"
            "protocols."
        ),
        validation_alias=AliasChoices("saslMechanism", "KAFKA_SASL_MECHANISM"),
    )

    sasl_username: str | None = Field(
        default=None,
        title="SASL username",
        description=(
            "The username to use for SASL authentication. "
            "This is only needed for the SASL_SSL and SASL_PLAINTEXT security"
            "protocols."
        ),
        validation_alias=AliasChoices("saslUsername", "KAFKA_SASL_USERNAME"),
    )

    sasl_password: SecretStr | None = Field(
        default=None,
        title="SASL password",
        description=(
            "The password to use for SASL authentication. "
            "This is only needed for the SASL_SSL and SASL_PLAINTEXT security"
            "protocols."
        ),
        validation_alias=AliasChoices("saslPassword", "KAFKA_SASL_PASSWORD"),
    )

    model_config = SettingsConfigDict(
        case_sensitive=False, extra="forbid", populate_by_name=True
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
        SslSettings
        | SaslSslSettings
        | SaslPlaintextSettings
        | PlaintextSettings
    ):
        """Return a model with a subset of settings for a Kafka auth method.

        This method will fail with a ValidationError if an invalid set of
        settings were provided.
        """
        match self.security_protocol:
            case SecurityProtocol.PLAINTEXT:
                return PlaintextSettings(**self.model_dump())
            case SecurityProtocol.SASL_SSL:
                return SaslSslSettings(**self.model_dump())
            case SecurityProtocol.SASL_PLAINTEXT:
                return SaslPlaintextSettings(**self.model_dump())
            case SecurityProtocol.SSL:
                return SslSettings(**self.model_dump())

    def to_faststream_params(self) -> FastStreamBrokerParams:
        return self.validated.to_faststream_params()

    def to_aiokafka_params(self) -> AIOKafkaParams:
        return self.validated.to_aiokafka_params()
