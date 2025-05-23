"""Kafka test container with listeners for different security protocols.

This test container is heavily inspired by the default Testcontainers_ `Kafka
test container
<https://github.com/testcontainers/testcontainers-python/blob/main/modules/kafka/testcontainers/kafka/__init__.py>`__,
but adds additional listeners for different security protocols. The key
changes are:

* Create SSL, SASL_SSL, and SASL_PLAINTEXT listeners in addition to the
  the PLAINTEXT listener.
* Expose the SASL username and password with ``get_sasl_username`` and
  ``get_sasl_password`` methods.
* Provide a ``get_secret_file_contents`` method to retrieve the TLS
  certificates created during startup.
* Provide a ``reset`` method to delete all topics from the running Kafka
  instance.
* Always limit the broker to the first host.
* Always use KRaft.
"""

import errno
import os
import sys
import tarfile
import time
from importlib import resources
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from typing import Any, Self

from testcontainers.core.container import DockerContainer
from testcontainers.core.version import ComparableVersion
from testcontainers.core.waiting_utils import wait_for_logs

from ._constants import CONFLUENT_VERSION_TAG, KAFKA_REPOSITORY

__all__ = ["FullKafkaContainer"]


class FullKafkaContainer(DockerContainer):
    """Kafka container.

    Examples
    --------

    .. code-block:: python

       from testcontainers.kafka import KafkaContainer

       with KafkaContainer() as kafka:
           connection = kafka.get_bootstrap_server()
    """

    _CLUSTER_ID = "MkU3OEVBNTcwNTJENDM2Qk"
    """Kafka cluster ID.

    This is arbitrary and has no special meaning. The cluster just needs some
    cluster ID and this is the one used as an example in some Kafka
    documentation.
    """

    _MIN_KRAFT_TAG = "7.0.0"
    """Minimum tag version for KRaft support."""

    _START_SCRIPT = "/tc-start.sh"
    """Path where the start script is stored in the container."""

    def __init__(
        self,
        image: str = f"{KAFKA_REPOSITORY}:{CONFLUENT_VERSION_TAG}",
        port: int = 9093,
        ssl_port: int = 29093,
        sasl_plaintext_port: int = 29094,
        sasl_ssl_port: int = 29095,
        **kwargs: Any,
    ) -> None:
        self._verify_min_kraft_version(image)
        super().__init__(image, **kwargs)

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

        self.container_cert_path = Path("/etc/kafka/secrets")
        self.sasl_username = "admin"
        self.sasl_password = "admin"

    def get_bootstrap_server(self) -> str:
        """Get the bootstrap server for a no TLS, no SASL connection."""
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        return f"{host}:{port}"

    def get_ssl_bootstrap_server(self) -> str:
        """Get the bootstrap server for a TLS connection."""
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.ssl_port)
        return f"{host}:{port}"

    def get_sasl_ssl_bootstrap_server(self) -> str:
        """Get the bootstrap server for a SASL TLS connection."""
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.sasl_ssl_port)
        return f"{host}:{port}"

    def get_sasl_plaintext_bootstrap_server(self) -> str:
        """Get the bootstrap server for a SASL PLAINTEXT connection."""
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.sasl_plaintext_port)
        return f"{host}:{port}"

    def get_sasl_username(self) -> str:
        """Get the configured SASL username for the Kafka listener."""
        return self.sasl_username

    def get_sasl_password(self) -> str:
        """Get the configured SASL password for the Kafka listener."""
        return self.sasl_password

    def start(self, timeout: int = 30) -> Self:
        """Start the container.

        Parameters
        ----------
        timeout
            How long to wait for the container to start before raising an
            error if Kafka still isn't running.
        """
        self._configure()

        # Create a start command that waits for the start script to be created
        # and then runs it. We have to do it this way because the start script
        # is not baked into the container and we can't add it to the
        # container until the container is started.
        script = self._START_SCRIPT
        command = (
            f'sh -c "while [ ! -f {script} ]; do sleep 0.1; done; sh {script}"'
        )
        self.with_command(command)

        # Start the container and then add the startup script, which should be
        # picked up and run.
        super().start()
        self._create_start_script()
        try:
            wait_for_logs(self, r".*Kafka Server started.*", timeout=timeout)
        except TimeoutError:
            output, errors = self.get_logs()
            sys.stderr.write(errors.decode())
            sys.stdout.write(output.decode())
            raise

        # Configure SASL.
        self.exec(
            f"kafka-configs --bootstrap-server localhost:9092 --alter "
            f"--add-config 'SCRAM-SHA-512=[iterations=8192,"
            f"password={self.sasl_password}]' --entity-type users "
            f"--entity-name {self.sasl_username}"
        )

        return self

    def create_file(self, content: bytes, path: str) -> None:
        """Create a file inside the container.

        Parameters
        ----------
        content
            Content of the file.
        path
            Path to the file inside the container.
        """
        with BytesIO() as archive:
            with tarfile.TarFile(fileobj=archive, mode="w") as tar:
                tarinfo = tarfile.TarInfo(name=path)
                tarinfo.size = len(content)
                tarinfo.mtime = int(time.time())
                tar.addfile(tarinfo, BytesIO(content))
                archive.seek(0)
                self.get_wrapped_container().put_archive("/", archive)

    def get_secret_file_contents(self, name: str) -> str:
        """Get the contents of a file from :file:`/etc/kafka/secrets`.

        Useful for getting TLS certs and keys for connecting with the SSL
        security protocol.

        We can't just mount a host volume over :file:`/etc/kafka/secrets`
        because the OS user that owns that directory could be different than
        that ``appuser`` user that runs kafka in the container.

        Parameters
        ----------
        name
            Name of the secret to retrieve. This should normally be one of
            :file:`ca.crt`, :file:`client.crt`, or :file:`client.key`.

        Raises
        ------
        FileNotFoundError
            Raised if the requested file could not be found in the
            :file:`/etc/kafka/secrets` directory.
        """
        path = self.container_cert_path / name
        bits, _ = self.get_wrapped_container().get_archive(str(path))
        with BytesIO() as raw:
            for chunk in bits:
                raw.write(chunk)
            raw.seek(0)
            with tarfile.open(fileobj=raw) as tf:
                stream = tf.extractfile(name)
                if not stream:
                    raise FileNotFoundError(
                        errno.ENOENT, os.strerror(errno.ENOENT), str(path)
                    )
                return stream.read().decode()

    def reset(self) -> None:
        """Reset all Kafka topics."""
        self.exec(
            "/bin/kafka-topics --bootstrap-server localhost:9092 --delete"
            " --topic '.*'"
        )

    def _configure(self) -> None:
        """Configure the container environment variables."""
        quorum_voters = f"1@{self._get_network_alias()}:9094"

        # Kafka
        self.with_env("CLUSTER_ID", self._CLUSTER_ID)
        self.with_env("KAFKA_BROKER_ID", "1")
        self.with_env("KAFKA_CONTROLLER_LISTENER_NAMES", "CONTROLLER")
        self.with_env("KAFKA_CONTROLLER_QUORUM_VOTERS", quorum_voters)
        self.with_env("KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS", "0")
        self.with_env(
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP",
            (
                "BROKER:PLAINTEXT,PLAINTEXT:PLAINTEXT,SSL:SSL,SASL_SSL:"
                "SASL_SSL,SASL_PLAINTEXT:SASL_PLAINTEXT,CONTROLLER:PLAINTEXT"
            ),
        )
        self.with_env("KAFKA_INTER_BROKER_LISTENER_NAME", "BROKER")
        self.with_env(
            "KAFKA_LISTENERS",
            (
                f"PLAINTEXT://0.0.0.0:{self.port},"
                "BROKER://0.0.0.0:9092,"
                f"SSL://0.0.0.0:{self.ssl_port},"
                f"SASL_SSL://0.0.0.0:{self.sasl_ssl_port},"
                f"SASL_PLAINTEXT://0.0.0.0:{self.sasl_plaintext_port},"
                "CONTROLLER://0.0.0.0:9094"
            ),
        )
        self.with_env("KAFKA_LOG_FLUSH_INTERVAL_MESSAGES", "10000000")
        self.with_env("KAFKA_NODE_ID", 1)
        self.with_env("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1")
        self.with_env("KAFKA_OFFSETS_TOPIC_NUM_PARTITIONS", "1")
        self.with_env("KAFKA_PROCESS_ROLES", "broker,controller")

        # SSL
        self.with_env("KAFKA_SSL_KEYSTORE_FILENAME", "server.keystore.jks")
        self.with_env("KAFKA_SSL_KEYSTORE_CREDENTIALS", "credentials")
        self.with_env("KAFKA_SSL_KEY_CREDENTIALS", "credentials")
        self.with_env("KAFKA_SSL_TRUSTSTORE_FILENAME", "server.truststore.jks")
        self.with_env("KAFKA_SSL_TRUSTSTORE_CREDENTIALS", "credentials")

        # SASL
        self.with_env("KAFKA_SASL_ENABLED_MECHANISMS", "SCRAM-SHA-512")
        self.with_env(
            "KAFKA_OPTS",
            (
                "-Djava.security.auth.login.config="
                f"{self.container_cert_path!s}/kafka_server_jaas.conf"
            ),
        )

    def _create_start_script(self) -> None:
        """Create the script to start the container."""
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        ssl_port = self.get_exposed_port(self.ssl_port)
        sasl_ssl_port = self.get_exposed_port(self.sasl_ssl_port)
        sasl_plaintext_port = self.get_exposed_port(self.sasl_plaintext_port)
        listeners = (
            f"PLAINTEXT://{host}:{port},"
            f"BROKER://$(hostname -i | cut -d' ' -f1):9092,"
            f"SSL://{host}:{ssl_port},SASL_SSL://{host}:{sasl_ssl_port},"
            f"SASL_PLAINTEXT://{host}:{sasl_plaintext_port}"
        )

        files = resources.files("safir.testing.containers").joinpath("data")
        with files.joinpath("generate-kafka-secrets.bash").open("r") as f:
            generate_certs_script = f.read().encode()
        self.create_file(generate_certs_script, "/generate-kafka-secrets.bash")

        data = (
            dedent(
                f"""
                #!/bin/bash
                /bin/bash /generate-kafka-secrets.bash \
                    {self.container_cert_path} {host}
                sed -i '/KAFKA_ZOOKEEPER_CONNECT/d' \
                    /etc/confluent/docker/configure
                echo 'kafka-storage format --ignore-formatted \
                  -t {self._CLUSTER_ID} -c /etc/kafka/kafka.properties' \
                  >> /etc/confluent/docker/configure
                export KAFKA_ADVERTISED_LISTENERS={listeners}
                . /etc/confluent/docker/bash-config
                /etc/confluent/docker/configure
                /etc/confluent/docker/launch
                """
            )
            .strip()
            .encode()
        )
        self.create_file(data, self._START_SCRIPT)

    def _get_network_alias(self) -> str | None:
        """Get the alias of the network, if any."""
        if self._network:
            fallback = [self._network.name or self._kwargs.get("network", [])]
            return next(iter(self._network_aliases or fallback), None)
        return "localhost"

    def _verify_min_kraft_version(self, image: str) -> None:
        """Verify that the image is new enough to suppot KRaft.

        Parameters
        ----------
        image
            Docker image to run.
        """
        actual_version = image.split(":")[-1]
        if ComparableVersion(actual_version) < self._MIN_KRAFT_TAG:
            raise ValueError(
                f"Provided Confluent Platform's version {actual_version} "
                f"is not supported (must be {self._MIN_KRAFT_TAG} or above)"
            )
