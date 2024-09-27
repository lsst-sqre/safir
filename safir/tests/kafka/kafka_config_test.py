"""Tests for the safir.kafka module."""

import os
from pathlib import Path
from unittest import mock

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.admin.client import AIOKafkaAdminClient
from faststream.kafka import KafkaBroker
from pydantic import SecretStr, ValidationError

from safir.kafka import (
    KafkaConnectionSettings,
    SaslMechanism,
    SecurityProtocol,
)

from ..support.kafka.container import FullKafkaContainer


async def assert_clients(settings: KafkaConnectionSettings) -> None:
    admin = None
    broker = None
    consumer = None

    try:
        admin = AIOKafkaAdminClient(**settings.to_aiokafka_params())
        await admin.start()
        await admin.list_topics()

        consumer = AIOKafkaConsumer(**settings.to_aiokafka_params())
        await consumer.start()

        broker = KafkaBroker(**settings.to_faststream_params())
        await broker.start()
        result = await broker.ping(timeout=5)
        assert result

    finally:
        if admin:
            await admin.close()
        if consumer:
            await consumer.stop()
        if broker:
            await broker.close()


@pytest.mark.asyncio
async def test_plaintext(
    monkeypatch: pytest.MonkeyPatch, kafka_container: FullKafkaContainer
) -> None:
    bootstrap_server = kafka_container.get_bootstrap_server()
    settings = KafkaConnectionSettings(
        bootstrap_servers=bootstrap_server,
        security_protocol=SecurityProtocol.PLAINTEXT,
    )
    await assert_clients(settings)

    with mock.patch.dict(os.environ, clear=True):
        envvars = {
            "KAFKA_BOOTSTRAP_SERVERS": bootstrap_server,
            "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        settings = KafkaConnectionSettings()
        await assert_clients(settings)


@pytest.mark.asyncio
async def test_sasl_plaintext(
    monkeypatch: pytest.MonkeyPatch, kafka_container: FullKafkaContainer
) -> None:
    bootstrap_server = kafka_container.get_sasl_plaintext_bootstrap_server()
    with pytest.raises(ValidationError):
        KafkaConnectionSettings(
            bootstrap_servers=bootstrap_server,
            security_protocol=SecurityProtocol.SASL_PLAINTEXT,
            sasl_mechanism=SaslMechanism.SCRAM_SHA_512,
            sasl_username="username",
        )

    settings = KafkaConnectionSettings(
        bootstrap_servers=bootstrap_server,
        security_protocol=SecurityProtocol.SASL_PLAINTEXT,
        sasl_username="admin",
        sasl_password=SecretStr("admin"),
        sasl_mechanism=SaslMechanism.SCRAM_SHA_512,
    )

    await assert_clients(settings)

    with mock.patch.dict(os.environ, clear=True):
        envvars = {
            "KAFKA_BOOTSTRAP_SERVERS": bootstrap_server,
            "KAFKA_SECURITY_PROTOCOL": "SASL_PLAINTEXT",
            "KAFKA_SASL_USERNAME": "admin",
            "KAFKA_SASL_PASSWORD": "admin",
            "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        settings = KafkaConnectionSettings()

        await assert_clients(settings)


@pytest.mark.asyncio
async def test_sasl_ssl(
    monkeypatch: pytest.MonkeyPatch,
    kafka_container: FullKafkaContainer,
    kafka_cert_path: Path,
) -> None:
    cluster_ca_path = kafka_cert_path / "ca.crt"

    bootstrap_server = kafka_container.get_sasl_ssl_bootstrap_server()
    with pytest.raises(ValidationError):
        KafkaConnectionSettings(
            bootstrap_servers=bootstrap_server,
            security_protocol=SecurityProtocol.SASL_SSL,
            sasl_username="admin",
            sasl_password=SecretStr("admin"),
            cluster_ca_path=cluster_ca_path,
        )

    settings = KafkaConnectionSettings(
        bootstrap_servers=bootstrap_server,
        security_protocol=SecurityProtocol.SASL_SSL,
        sasl_username="admin",
        sasl_password=SecretStr("admin"),
        sasl_mechanism=SaslMechanism.SCRAM_SHA_512,
        cluster_ca_path=cluster_ca_path,
    )

    await assert_clients(settings)

    with mock.patch.dict(os.environ, clear=True):
        envvars = {
            "KAFKA_BOOTSTRAP_SERVERS": bootstrap_server,
            "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
            "KAFKA_SASL_USERNAME": "admin",
            "KAFKA_SASL_PASSWORD": "admin",
            "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
            "KAFKA_CLUSTER_CA_PATH": str(cluster_ca_path),
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        settings = KafkaConnectionSettings()

        await assert_clients(settings)


@pytest.mark.asyncio
async def test_ssl(
    kafka_cert_path: Path,
    kafka_container: FullKafkaContainer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cluster_ca_path = kafka_cert_path / "ca.crt"
    client_cert_path = kafka_cert_path / "client.crt"
    client_key_path = kafka_cert_path / "client.key"

    bootstrap_server = kafka_container.get_ssl_bootstrap_server()
    with pytest.raises(ValidationError):
        KafkaConnectionSettings(
            bootstrap_servers=bootstrap_server,
            security_protocol=SecurityProtocol.SSL,
            cluster_ca_path=cluster_ca_path,
            client_cert_path=client_cert_path,
        )

    settings = KafkaConnectionSettings(
        bootstrap_servers=bootstrap_server,
        security_protocol=SecurityProtocol.SSL,
        cluster_ca_path=cluster_ca_path,
        client_cert_path=client_cert_path,
        client_key_path=client_key_path,
    )

    await assert_clients(settings)

    with mock.patch.dict(os.environ, clear=True):
        envvars = {
            "KAFKA_BOOTSTRAP_SERVERS": bootstrap_server,
            "KAFKA_SECURITY_PROTOCOL": "SSL",
            "KAFKA_CLUSTER_CA_PATH": str(cluster_ca_path),
            "KAFKA_CLIENT_CERT_PATH": str(client_cert_path),
            "KAFKA_CLIENT_KEY_PATH": str(client_key_path),
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        settings = KafkaConnectionSettings()

        await assert_clients(settings)
