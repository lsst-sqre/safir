"""Constants for use in tests."""

from pathlib import Path

CONFLUENT_VERSION_TAG = "7.6.0"
"""Docker image tag for Confluent images like kafka and the schema registry."""

DATA_DIR = Path(__file__).parent / "data"
"""Absolute path to the test data directory"""
