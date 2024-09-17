from typing import Any

from testcontainers.core.network import Network
from testcontainers.kafka import KafkaContainer

from tests.constants import CONFLUENT_VERSION_TAG


class NetworkedKafkaContainer(KafkaContainer):
    def __init__(
        self,
        network: Network,
        image: str = f"confluentinc/cp-kafka:{CONFLUENT_VERSION_TAG}",
        port: int = 9093,
        **kwargs: dict[str, Any],
    ) -> None:
        super().__init__(image=image, port=port, **kwargs)
        self.with_network(network)
        self.with_network_aliases("kafka")

    def reset(self) -> None:
        self.exec(
            "/bin/kafka-topics --bootstrap-server localhost:9092 --delete"
            " --topic '.*'"
        )
