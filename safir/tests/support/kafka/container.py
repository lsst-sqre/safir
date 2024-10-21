"""Kafka Testcontainer with listeners for different security protocols.

This is the testcontainers built-in module:
https://github.com/testcontainers/testcontainers-python/blob/main/modules/kafka/testcontainers/kafka/__init__.py

With these differences:
* Provision SSL, SASL_SSL, and SASL_PLAINTEXT listeners in addition to the
  existing PLAINTEXT listener.
* Optionally mount a host directory for the generated kafka ssl secrets so
  they can be used in test clients
* Expose the SASL username and password with ``.get_sasl_username()`` and
  ``.get_sasl_password()``
* Provide ``.reset()`` to delete all topics from the running kafka instance
* Optionally control ``limit_broker_to_first_host`` with an init var
  instead of an env var
* Always uses Kraft, no more Zookeeper
* Type annotation fixes
* Lint fixes
"""

import tarfile
import time
from dataclasses import dataclass, field
from io import BytesIO
from os import environ
from pathlib import Path
from textwrap import dedent
from typing import Any, Self

from testcontainers.core.container import DockerContainer
from testcontainers.core.utils import raise_for_deprecated_parameter
from testcontainers.core.version import ComparableVersion
from testcontainers.core.waiting_utils import wait_for_logs

__all__ = [
    "FullKafkaContainer",
    "kafka_config",
]
LIMIT_BROKER_ENV_VAR = "TC_KAFKA_LIMIT_BROKER_TO_FIRST_HOST"


@dataclass
class _KafkaConfig:
    limit_broker_to_first_host: bool = field(
        default_factory=lambda: environ.get(LIMIT_BROKER_ENV_VAR) == "true"
    )
    """
    This option is useful for a setup with a network,
    see testcontainers/testcontainers-python#637 for more details
    """


kafka_config = _KafkaConfig()


class FullKafkaContainer(DockerContainer):
    """
    Kafka container.

    Example:

        .. doctest::

            >>> from testcontainers.kafka import KafkaContainer

            >>> with KafkaContainer() as kafka:
            ...     connection = kafka.get_bootstrap_server()
            ...

            # Using KRaft protocol
            >>> with KafkaContainer().with_kraft() as kafka:
            ...     connection = kafka.get_bootstrap_server()
            ...
    """  # fmt: skip

    TC_START_SCRIPT = "/tc-start.sh"
    MIN_KRAFT_TAG = "7.0.0"

    def __init__(
        self,
        image: str = "confluentinc/cp-kafka:7.6.0",
        port: int = 9093,
        ssl_port: int = 29093,
        sasl_plaintext_port: int = 29094,
        sasl_ssl_port: int = 29095,
        limit_broker_to_first_host: bool | None = None,
        **kwargs: Any,
    ) -> None:
        raise_for_deprecated_parameter(kwargs, "port_to_expose", "port")
        super().__init__(image, **kwargs)

        self.limit_broker_to_first_host = (
            limit_broker_to_first_host
            if limit_broker_to_first_host is not None
            else kafka_config.limit_broker_to_first_host
        )
        self.container_cert_path = Path("/etc/kafka/secrets")
        self.host_cert_script_path = Path(__file__).parent / "data"
        self.container_cert_script_path = Path(
            "/var/generate-kafka-certs.bash"
        )
        self.with_volume_mapping(
            host=str(self.host_cert_script_path),
            container="/var/testcontainers-init",
            mode="ro",
        )

        self.port = port
        self.sasl_plaintext_port = sasl_plaintext_port
        self.ssl_port = ssl_port
        self.sasl_ssl_port = sasl_ssl_port
        self.with_exposed_ports(
            self.port,
            self.ssl_port,
            self.sasl_plaintext_port,
            self.sasl_ssl_port,
        )

        self.sasl_username = "admin"
        self.sasl_password = "admin"

        # Kraft
        self.wait_for = r".*\[KafkaServer id=\d+\] started.*"
        self.boot_command = ""
        self.cluster_id = "MkU3OEVBNTcwNTJENDM2Qk"
        self.listeners = (
            f"PLAINTEXT://0.0.0.0:{self.port},BROKER://0.0.0.0:9092,"
            f"SSL://0.0.0.0:{self.ssl_port},"
            f"SASL_SSL://0.0.0.0:{self.sasl_ssl_port},"
            f"SASL_PLAINTEXT://0.0.0.0:{self.sasl_plaintext_port}"
        )

        self.security_protocol_map = (
            "BROKER:PLAINTEXT,PLAINTEXT:PLAINTEXT,SSL:SSL,SASL_SSL:SASL_SSL,"
            "SASL_PLAINTEXT:SASL_PLAINTEXT"
        )

        self.with_env("KAFKA_LISTENERS", self.listeners)
        self.with_env(
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP", self.security_protocol_map
        )
        self.with_env("KAFKA_INTER_BROKER_LISTENER_NAME", "BROKER")

        self.with_env("KAFKA_BROKER_ID", "1")
        self.with_env("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1")
        self.with_env("KAFKA_OFFSETS_TOPIC_NUM_PARTITIONS", "1")
        self.with_env("KAFKA_LOG_FLUSH_INTERVAL_MESSAGES", "10000000")
        self.with_env("KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS", "0")

        # SSL
        self.with_env("KAFKA_SSL_KEYSTORE_FILENAME", "server.keystore.jks")
        self.with_env("KAFKA_SSL_KEYSTORE_CREDENTIALS", "credentials")
        self.with_env("KAFKA_SSL_KEY_CREDENTIALS", "credentials")
        self.with_env(
            "KAFKA_SSL_TRUSTSTORE_FILENAME",
            "server.truststore.jks",
        )
        self.with_env("KAFKA_SSL_TRUSTSTORE_CREDENTIALS", "credentials")

        # SASL
        self.with_env("KAFKA_SASL_ENABLED_MECHANISMS", "SCRAM-SHA-512")
        self.with_env(
            "KAFKA_OPTS",
            f"-Djava.security.auth.login.config={self.container_cert_path!s}/kafka_server_jaas.conf",
        )

        self._verify_min_kraft_version()
        self.kraft_enabled = True

    def _verify_min_kraft_version(self) -> None:
        actual_version = self.image.split(":")[-1]

        if ComparableVersion(actual_version) < self.MIN_KRAFT_TAG:
            raise ValueError(
                f"Provided Confluent Platform's version {actual_version} "
                f"is not supported in Kraft mode"
                f" (must be {self.MIN_KRAFT_TAG} or above)"
            )

    def with_cluster_id(self, cluster_id: str) -> Self:
        self.cluster_id = cluster_id
        return self

    def configure(self) -> None:
        self.wait_for = r".*Kafka Server started.*"

        self.with_env("CLUSTER_ID", self.cluster_id)
        self.with_env("KAFKA_NODE_ID", 1)
        self.with_env(
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP",
            f"{self.security_protocol_map},CONTROLLER:PLAINTEXT",
        )
        self.with_env(
            "KAFKA_LISTENERS",
            f"{self.listeners},CONTROLLER://0.0.0.0:9094",
        )
        self.with_env("KAFKA_PROCESS_ROLES", "broker,controller")

        network_alias = self._get_network_alias()
        controller_quorum_voters = f"1@{network_alias}:9094"
        self.with_env(
            "KAFKA_CONTROLLER_QUORUM_VOTERS", controller_quorum_voters
        )
        self.with_env("KAFKA_CONTROLLER_LISTENER_NAMES", "CONTROLLER")

        self.boot_command = f"""
                    sed -i '/KAFKA_ZOOKEEPER_CONNECT/d' \
                      /etc/confluent/docker/configure
                    echo 'kafka-storage format --ignore-formatted \
                      -t {self.cluster_id} -c /etc/kafka/kafka.properties' \
                      >> /etc/confluent/docker/configure
                """

    def _get_network_alias(self) -> str | None:
        if self._network:
            return next(
                iter(
                    self._network_aliases
                    or [self._network.name or self._kwargs.get("network", [])]
                ),
                None,
            )

        return "localhost"

    def get_bootstrap_server(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        return f"{host}:{port}"

    def get_ssl_bootstrap_server(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.ssl_port)
        return f"{host}:{port}"

    def get_sasl_ssl_bootstrap_server(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.sasl_ssl_port)
        return f"{host}:{port}"

    def get_sasl_plaintext_bootstrap_server(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.sasl_plaintext_port)
        return f"{host}:{port}"

    def get_sasl_username(self) -> str:
        return self.sasl_username

    def get_sasl_password(self) -> str:
        return self.sasl_password

    def tc_start(self) -> None:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        ssl_port = self.get_exposed_port(self.ssl_port)
        sasl_ssl_port = self.get_exposed_port(self.sasl_ssl_port)
        sasl_plaintext_port = self.get_exposed_port(self.sasl_plaintext_port)

        if self.limit_broker_to_first_host:
            listeners = (
                f"PLAINTEXT://{host}:{port},"
                f"BROKER://$(hostname -i | cut -d' ' -f1):9092,"
                f"SSL://{host}:{ssl_port},SASL_SSL://{host}:{sasl_ssl_port},"
                f"SASL_PLAINTEXT://{host}:{sasl_plaintext_port}"
            )
        else:
            listeners = (
                f"PLAINTEXT://{host}:{port},"
                f"BROKER://$(hostname -i):9092,SSL://{host}:{port},"
                f"SASL_SSL://{host}:{sasl_ssl_port},"
                f"SASL_PLAINTEXT://{host}:{sasl_plaintext_port}"
            )
        data = (
            dedent(
                f"""
                #!/bin/bash
                /var/testcontainers-init/generate-kafka-secrets.bash \
                  {self.container_cert_path!s} {host}
                {self.boot_command}
                export KAFKA_ADVERTISED_LISTENERS={listeners}
                . /etc/confluent/docker/bash-config
                /etc/confluent/docker/configure
                /etc/confluent/docker/launch
                """
            )
            .strip()
            .encode("utf-8")
        )
        self.create_file(data, self.TC_START_SCRIPT)

    def start(self, timeout: int = 30) -> Self:
        script = self.TC_START_SCRIPT
        command = (
            f'sh -c "while [ ! -f {script} ]; do sleep 0.1; done; sh {script}"'
        )
        self.configure()
        self.with_command(command)
        super().start()
        self.tc_start()
        wait_for_logs(self, self.wait_for, timeout=timeout)
        self.exec(
            f"kafka-configs --bootstrap-server localhost:9092 --alter "
            f"--add-config 'SCRAM-SHA-512=[iterations=8192,"
            f"password={self.sasl_password}]' --entity-type users "
            f"--entity-name {self.sasl_username}"
        )
        return self

    def get_secret_file_contents(self, name: str) -> str:
        """Get the contents of a file from /etc/kafka/secrets.

        Useful for getting TLS certs and keys for connecting with the SSL
        security protocol.

        We can't just mount a host volume over /etc/kafka/secrets because the
        OS user that owns that directory could be different than that
        ``appuser`` user that runs kafka in the container.
        """
        raw = BytesIO()
        path = Path("/etc/kafka/secrets/") / name
        bits, _ = self.get_wrapped_container().get_archive(str(path))
        for chunk in bits:
            raw.write(chunk)
        raw.seek(0)
        with tarfile.open(fileobj=raw) as tf:
            stream = tf.extractfile(name)
            assert stream
            data = stream.read()
            assert data
            return data.decode()

    def reset(self) -> None:
        self.exec(
            "/bin/kafka-topics --bootstrap-server localhost:9092 --delete"
            " --topic '.*'"
        )

    def create_file(self, content: bytes, path: str) -> None:
        with (
            BytesIO() as archive,
            tarfile.TarFile(fileobj=archive, mode="w") as tar,
        ):
            tarinfo = tarfile.TarInfo(name=path)
            tarinfo.size = len(content)
            tarinfo.mtime = int(time.time())
            tar.addfile(tarinfo, BytesIO(content))
            archive.seek(0)
            self.get_wrapped_container().put_archive("/", archive)
