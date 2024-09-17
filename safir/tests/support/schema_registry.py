from typing import Any, Self

import httpx
from httpx import ReadError, RemoteProtocolError
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.waiting_utils import wait_container_is_ready

from ..constants import CONFLUENT_VERSION_TAG

__all__ = ["NetworkedSchemaRegistryContainer"]


class NetworkedSchemaRegistryContainer(DockerContainer):
    def __init__(
        self,
        network: Network,
        kafka_bootstrap_servers: str = "kafka:9092",
        image: str = f"confluentinc/cp-schema-registry:{CONFLUENT_VERSION_TAG}",
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
        self.with_network(network)
        self.with_network_aliases("schemaregistry")

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
        url = f"{self.get_url()}/subjects"
        httpx.get(url, timeout=5).raise_for_status()
