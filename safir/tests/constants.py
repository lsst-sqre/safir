"""Constants for use in tests."""

CONFLUENT_VERSION_TAG = "7.6.0"
"""Docker image tag for Confluent images like kafka and the schema registry."""

KAFKA_DOCKER_IMAGE = f"confluentinc/cp-kafka:{CONFLUENT_VERSION_TAG}"
"""Docker image for Kafka Testcontainer"""

SCHEMA_REGISTRY_DOCKER_IMAGE = (
    f"confluentinc/cp-schema-registry:{CONFLUENT_VERSION_TAG}"
)
"""Docker image for schema registry Testcontainer"""
