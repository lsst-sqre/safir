from pathlib import Path

from testcontainers.compose import DockerCompose

__all__ = ["kafka_docker_compose_stack"]

path = Path(__file__).parent / "data"

kafka_docker_compose_stack = DockerCompose(path, pull=True)
