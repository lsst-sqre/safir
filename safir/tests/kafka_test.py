"""Tests for the safir.kafka module."""

import os
from unittest import mock

import pytest
from pydantic import SecretStr, ValidationError

from safir.kafka.aiokafka_admin_client import make_kafka_admin_client
from safir.kafka.aiokafka_consumer import make_kafka_consumer
from safir.kafka.config import KafkaConnectionSettings, KafkaSecurityProtocol
from safir.kafka.faststream_kafka_broker import make_kafka_broker
from tests.constants import DATA_DIR


async def make_clients(settings: KafkaConnectionSettings) -> None:
    make_kafka_consumer(settings, client_id="consumer")
    make_kafka_admin_client(settings, client_id="admin")
    make_kafka_broker(settings, client_id="broker")


@pytest.mark.asyncio
async def test_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = KafkaConnectionSettings(
        bootstrap_servers="some.domain:1234",
        security_protocol=KafkaSecurityProtocol.PLAINTEXT,
    )
    await make_clients(settings)

    with mock.patch.dict(os.environ, clear=True):
        envvars = {
            "KAFKA_BOOTSTRAP_SERVERS": "some.domain:1234",
            "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        settings = KafkaConnectionSettings()
        await make_clients(settings)


@pytest.mark.asyncio
async def test_sasl_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        KafkaConnectionSettings(
            bootstrap_servers="some.domain:1234",
            security_protocol=KafkaSecurityProtocol.SASL_PLAINTEXT,
        )

    settings = KafkaConnectionSettings(
        bootstrap_servers="some.domain:1234",
        security_protocol=KafkaSecurityProtocol.SASL_PLAINTEXT,
        sasl_username="username",
        sasl_password=SecretStr("password"),
    )

    await make_clients(settings)

    with mock.patch.dict(os.environ, clear=True):
        envvars = {
            "KAFKA_BOOTSTRAP_SERVERS": "some.domain:1234",
            "KAFKA_SECURITY_PROTOCOL": "SASL_PLAINTEXT",
            "KAFKA_SASL_USERNAME": "username",
            "KAFKA_SASL_PASSWORD": "password",
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        settings = KafkaConnectionSettings()

        await make_clients(settings)


@pytest.mark.asyncio
async def test_sasl_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        KafkaConnectionSettings(
            bootstrap_servers="some.domain:1234",
            security_protocol=KafkaSecurityProtocol.SASL_SSL,
        )

    settings = KafkaConnectionSettings(
        bootstrap_servers="some.domain:1234",
        security_protocol=KafkaSecurityProtocol.SASL_SSL,
        sasl_username="username",
        sasl_password=SecretStr("password"),
    )

    await make_clients(settings)

    with mock.patch.dict(os.environ, clear=True):
        envvars = {
            "KAFKA_BOOTSTRAP_SERVERS": "some.domain:1234",
            "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
            "KAFKA_SASL_USERNAME": "username",
            "KAFKA_SASL_PASSWORD": "password",
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        settings = KafkaConnectionSettings()

        await make_clients(settings)


@pytest.mark.asyncio
async def test_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    cluster_ca_path = DATA_DIR / "kafka" / "dummy-server-ca.crt"
    client_cert_path = DATA_DIR / "kafka" / "dummy-user.crt"
    client_key_path = DATA_DIR / "kafka" / "dummy-user.key"

    with pytest.raises(ValidationError):
        KafkaConnectionSettings(
            bootstrap_servers="some.domain:1234",
            security_protocol=KafkaSecurityProtocol.SSL,
            cluster_ca_path=cluster_ca_path,
            client_cert_path=client_cert_path,
        )

    settings = KafkaConnectionSettings(
        bootstrap_servers="some.domain:1234",
        security_protocol=KafkaSecurityProtocol.SSL,
        cluster_ca_path=cluster_ca_path,
        client_cert_path=client_cert_path,
        client_key_path=client_key_path,
    )

    await make_clients(settings)

    with mock.patch.dict(os.environ, clear=True):
        envvars = {
            "KAFKA_BOOTSTRAP_SERVERS": "some.domain:1234",
            "KAFKA_SECURITY_PROTOCOL": "SSL",
            "KAFKA_CLUSTER_CA_PATH": str(cluster_ca_path),
            "KAFKA_CLIENT_CERT_PATH": str(client_cert_path),
            "KAFKA_CLIENT_KEY_PATH": str(client_key_path),
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        settings = KafkaConnectionSettings()

        await make_clients(settings)
