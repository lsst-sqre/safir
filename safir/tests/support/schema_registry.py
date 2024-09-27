"""Helpers for tests that require a Confluent schema registry."""

from typing import Any, Self

import httpx
from httpx import ReadError, RemoteProtocolError
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.waiting_utils import wait_container_is_ready

from ..constants import SCHEMA_REGISTRY_DOCKER_IMAGE

__all__ = ["SchemaRegistryContainer"]


class SchemaRegistryContainer(DockerContainer):
    """A ``Testcontainers <https://github.com/testcontainers/testcontainers-python>``
    Confluent schema registry container.

    Parameters
    ----------
    network
        A Docker network to put this container in.
        The kafa container that will serve as storage must be on the same
        network.
    kafka_bootstrap_servers
        A string with a comma-separated list of kafka boostrap servers for the
        kafka instance that will serve as storage
    image
        The docker image to use.
    """

    def __init__(
        self,
        network: Network,
        kafka_bootstrap_servers: str = "kafka:9092",
        image: str = SCHEMA_REGISTRY_DOCKER_IMAGE,
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
        super().start(*args, **kwargs)
        self.health()
        return self

    def get_url(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        return f"http://{host}:{port}"

    def reset(self) -> None:
        url = f"{self.get_url()}/subjects"
        subjects = httpx.get(url).json()
        for subject in subjects:
            httpx.delete(f"{url}/{subject}")
            httpx.delete(f"{url}/{subject}?permanent=true")

    @wait_container_is_ready(ReadError, RemoteProtocolError)
    def health(self) -> None:
        """We're health when we can be queried from the host network."""
        url = f"{self.get_url()}/subjects"
        httpx.get(url, timeout=5).raise_for_status()
