"""Utilities for integrating with SQuaRE Events (Kafka)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from aiokafka import AIOKafkaProducer
from kafkit.ssl import concatenate_certificates, create_ssl_context

__all__ = ["configure_kafka_ssl", "init_kafka_producer"]

if TYPE_CHECKING:
    from typing import AsyncGenerator
    from aiohttp.web import Application


async def configure_kafka_ssl(app: Application) -> AsyncGenerator:
    """Configure an SSL context for the Kafka client (if appropriate).

    Parameters
    ----------
    app : `aiohttp.web.Application`
        The aiohttp.web-based application. This app *must* include a standard
        configuration object at the ``"safir/config"`` key. The config must
        have these attributes:

        ``logger_name``
            Name of the application's logger.
        ``kafka_protocol``
            The protocol for Kafka broker communication. Must be ``"SSL"``
            to make the SSL context (this function is a no-op otherwise).
        ``kafka_cluster_ca_path``
            Local file path of the Kafka cluster CA.
        ``kafka_client_ca_path``
            Local file path of the Kafka client CA.
        ``kafka_client_cert_path``
            Local file path of the Kafka client cert.
        ``kafka_client_key_path``
            Local file path of the Kafka client key.

    Notes
    -----
    If the ``config.kafka_protocol`` configuration is ``SSL``, this function
    sets up an SSL context (`ssl.create_default_context) using the certificates
    generated by Strimzi for the Kafka brokers and for this specific client.

    The SSL context is stored on the application under the
    ``safir/kafka_ssl_context`` key.

    Examples
    --------
    Use this function as a `cleanup context
    <https://aiohttp.readthedocs.io/en/stable/web_reference.html#aiohttp.web.Application.cleanup_ctx>`__:

    .. code-block:: python

       app.cleanup_ctx.append(configure_kafka_ssl)
    """
    logger = structlog.get_logger(app["safir/config"].logger_name)

    ssl_context_key = "safir/kafka_ssl_context"

    if app["safir/config"].kafka_protocol != "SSL":
        app[ssl_context_key] = None
        logger.info("Connecting to Kafka without SSL")

    else:
        client_cert_path = Path("./kafka_client.crt")
        client_cert_path = concatenate_certificates(
            cert_path=app["safir/config"].kafka_client_cert_path,
            ca_path=app["safir/config"].kafka_client_ca_path,
            output_path=client_cert_path,
        )
        ssl_context = create_ssl_context(
            cluster_ca_path=app["safir/config"].kafka_cluster_ca_path,
            client_cert_path=client_cert_path,
            client_key_path=app["safir/config"].kafka_client_key_path,
        )

        app[ssl_context_key] = ssl_context

        logger.info("Created Kafka SSL context")

    yield


async def init_kafka_producer(app: Application) -> AsyncGenerator:
    """Initialize and cleanup the aiokafka producer instance.

    Parameters
    ----------
    app : `aiohttp.web.Application`
        The aiohttp.web-based application. This app *must* include a standard
        configuration object at the ``"safir/config"`` key. The config must
        have these attributes:

        ``logger_name``
            Name of the application's logger.
        ``kafka_broker_url``
            The URL of a Kafka broker.
        ``kafka_protocol``
            The protocol for Kafka broker communication.

        Additionally, `configure_kafka_ssl` must be applied **before** this
        initializer so that ``safir/kafka_ssl_context`` is set on the
        application.

    Notes
    -----
    This initializer adds an `aiokafka.AIOKafkaProducer` instance to the
    ``app`` under the ``safir/kafka_producer`` key.

    If the ``kafka_broker_url`` configuration key has a value of `None`, then
    the value of ``safir/kafka_producer`` is `None`.

    Examples
    --------
    Use this function as a `cleanup context
    <https://aiohttp.readthedocs.io/en/stable/web_reference.html#aiohttp.web.Application.cleanup_ctx>`__.

    To access the producer:

    .. code-block:: python

       producer = app["safir/kafka_producer"]
    """
    logger = structlog.get_logger(app["safir/config"].logger_name)

    # Startup phase
    kafka_broker_url = app["safir/config"].kafka_broker_url

    if kafka_broker_url is None:
        logger.info("Skipping Kafka producer initialization")
        producer = None

    else:
        logger.info("Starting Kafka producer")
        producer = AIOKafkaProducer(
            loop=asyncio.get_running_loop(),
            bootstrap_servers=kafka_broker_url,
            ssl_context=app["safir/kafka_ssl_context"],
            security_protocol=app["safir/config"].kafka_protocol,
        )
        await producer.start()
        app["safir/kafka_producer"] = producer
        logger.info("Finished starting Kafka producer")

    yield

    # Cleanup phase
    if producer is not None:
        logger.info("Shutting down Kafka producer")
        await producer.stop()
