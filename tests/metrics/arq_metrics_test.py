"""Tests for generic arq metrics functionality."""

from collections.abc import Callable
from typing import cast

import pytest
from arq.connections import ArqRedis, RedisSettings

from safir.metrics import (
    NOT_NONE,
    EventsConfiguration,
    MockEventPublisher,
    MockMetricsConfiguration,
)
from safir.metrics.arq import (
    ARQ_EVENTS_CONTEXT_KEY,
    ArqEvents,
    ArqMetricsError,
    initialize_arq_metrics,
    make_on_job_start,
    publish_queue_stats,
)


async def somejob(_ctx: dict) -> int:
    return 100


@pytest.mark.asyncio
async def test_arq_metrics(
    arq_redis: ArqRedis,
    create_arq_worker: Callable,
) -> None:
    # A variable to close over where we can put the container that
    # initialize_arq_metrics injects into the context so that we can assert
    # things about the events that were published
    events: ArqEvents | None = None

    # A startup function that initializes and event manager and calls
    # initialize_arq_metrics
    async def startup(ctx: dict) -> None:
        nonlocal events
        config = MockMetricsConfiguration(
            application="testapp",
            enabled=False,
            events=EventsConfiguration(topic_prefix="what.ever"),
            mock=True,
        )
        event_manager = config.make_manager()
        await event_manager.initialize()

        await initialize_arq_metrics(event_manager, ctx)
        events = ctx[ARQ_EVENTS_CONTEXT_KEY]

    # Create a real Arq worker
    queue_name = "some_queue"
    on_job_start = make_on_job_start(queue_name=queue_name)
    worker = create_arq_worker(
        functions=[somejob],
        queue_name=queue_name,
        on_startup=startup,
        on_job_start=on_job_start,
    )

    # Enqueue a job
    job = await arq_redis.enqueue_job("somejob", _queue_name=queue_name)
    assert job

    # Start the worker
    await worker.main()
    assert worker.jobs_complete == 1

    # Make sure the with_arq_metrics decorator didn't ruin our result
    result = await job.result()
    assert result == 100

    # Make sure the on_job_start function to published the right events
    assert events is not None
    publisher = cast("MockEventPublisher", events.arq_queue_job_event)
    publisher.published.assert_published_all(
        [
            {
                "time_in_queue": NOT_NONE,
                "queue": queue_name,
            }
        ]
    )


@pytest.mark.asyncio
async def test_arq_metrics_misconfiguration(
    arq_redis: ArqRedis,
    create_arq_worker: Callable,
) -> None:
    # A startup function that initializes and event manager but DOESN'T call
    # initialize_arq_metrics
    async def startup(ctx: dict) -> None:
        config = MockMetricsConfiguration(
            application="testapp",
            enabled=False,
            events=EventsConfiguration(topic_prefix="what.ever"),
            mock=True,
        )
        event_manager = config.make_manager()
        await event_manager.initialize()

    # Create a real Arq worker
    queue_name = "some_queue"
    on_job_start = make_on_job_start(queue_name=queue_name)
    worker = create_arq_worker(
        functions=[somejob],
        queue_name=queue_name,
        on_startup=startup,
        on_job_start=on_job_start,
    )
    # Enqueue a job
    job = await arq_redis.enqueue_job("somejob", _queue_name=queue_name)
    assert job

    # Start the worker
    with pytest.raises(ArqMetricsError):
        await worker.main()


@pytest.mark.asyncio
async def test_publish_queue_stats(arq_redis: ArqRedis) -> None:
    config = MockMetricsConfiguration(
        application="testapp",
        enabled=False,
        events=EventsConfiguration(topic_prefix="what.ever"),
        mock=True,
    )
    manager = config.make_manager()
    await manager.initialize()
    events = ArqEvents()
    await events.initialize(manager)

    queue_name = "some_queue"

    # Enqueue 5 jobs
    for _ in range(5):
        await arq_redis.enqueue_job("somejob", _queue_name=queue_name)

    # Publish stats
    host = arq_redis.connection_pool.connection_kwargs["host"]
    port = arq_redis.connection_pool.connection_kwargs["port"]

    redis_settings = RedisSettings(host=host, port=port)
    await publish_queue_stats(
        queue=queue_name, redis_settings=redis_settings, arq_events=events
    )

    # Check our published events
    publisher = cast("MockEventPublisher", events.arq_queue_stats)
    publisher.published.assert_published_all(
        [{"num_queued": 5, "queue": queue_name}]
    )
