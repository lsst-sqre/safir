"""Docker container for testing with a Kafka Confluent schema registry."""

from __future__ import annotations

from typing import Any, Self

import httpx
from httpx import ReadError, RemoteProtocolError
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.waiting_utils import wait_container_is_ready

from ._constants import CONFLUENT_VERSION_TAG, SCHEMA_REGISTRY_REPOSITORY

__all__ = ["SchemaRegistryContainer"]


class SchemaRegistryContainer(DockerContainer):
    """A Testcontainers_ Confluent schema registry container.

    Parameters
    ----------
    network
        Docker network to put this container in. The Kafa container that will
        serve as storage must be on the same network.
    kafka_bootstrap_servers
        Comma-separated list of Kafka boostrap servers for the Kafka instance
        that will serve as storage.
    image
        Docker image to use.
    """

    def __init__(
        self,
        network: Network,
        kafka_bootstrap_servers: str = "kafka:9092",
        image: str = f"{SCHEMA_REGISTRY_REPOSITORY}:{CONFLUENT_VERSION_TAG}",
        **kwargs: dict[str, Any],
    ) -> None:
        super().__init__(image, **kwargs)
        self.port = 8081
        self.with_exposed_ports(self.port)
        self.with_env(
            "SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS",
            kafka_bootstrap_servers,
        )
        self.with_env("SCHEMA_REGISTRY_LISTENERS", "http://0.0.0.0:8081")
        self.with_env(
            "SCHEMA_REGISTRY_HOST_NAME", self.get_container_host_ip()
        )

    def start(self, *args: list[Any], **kwargs: dict[str, Any]) -> Self:
        """Start the container.

        Wait for health after starting the container. Any arguments are
        passed verbatim to the standard testcontainers start method.
        """
        super().start(*args, **kwargs)
        self.health()
        return self

    def get_url(self) -> str:
        """Construct the URL to the schema registry."""
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        return f"http://{host}:{port}"

    def reset(self) -> None:
        """Reset the contents of the schema registry to its initial state."""
        url = f"{self.get_url()}/subjects"
        subjects = httpx.get(url).json()
        for subject in subjects:
            httpx.delete(f"{url}/{subject}")
            httpx.delete(f"{url}/{subject}?permanent=true")

    @wait_container_is_ready(ReadError, RemoteProtocolError)
    def health(self) -> None:
        """Check the health of the container.

        Consider the container healthy once the schema registry can be
        contacted from the host network.
        """
        url = f"{self.get_url()}/subjects"
        httpx.get(url, timeout=5).raise_for_status()
