"""Constants for use in tests."""

from pathlib import Path

CONFLUENT_VERSION_TAG = "7.6.0"
"""Docker image tag for Confluent images like kafka and the schema registry."""

KAFKA_DOCKER_IMAGE = f"confluentinc/cp-kafka:{CONFLUENT_VERSION_TAG}"
"""Docker image for Kafka Testcontainer"""

SCHEMA_REGISTRY_DOCKER_IMAGE = (
    f"confluentinc/cp-schema-registry:{CONFLUENT_VERSION_TAG}"
)
"""Docker image for schema registry Testcontainer"""

CERT_MAKER_DOCKER_IMAGE = KAFKA_DOCKER_IMAGE
"""Docker image for the cert maker Testcontainer"""

DATA_DIR = Path(__file__).parent / "data"
"""Absolute path to the test data directory"""
