"""Tools for collecting generic metrics for Arq jobs and queues.

This module is importable separately from the rest of the metrics package
because it depends on the ``arq`` package, which is only installed with the
optional ``safir[arq]`` extra.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any

try:
    from arq.connections import RedisSettings, create_pool
    from arq.typing import StartupShutdown
except ImportError as e:
    raise ImportError(
        "The safir.metrics.arq module requires the kafka and arq extras. "
        "Install it with `pip install safir[arq,kafka]`."
    ) from e
from pydantic import BaseModel, ConfigDict, Field

from safir.datetime._current import current_datetime

from ._event_manager import EventManager
from ._models import EventPayload

__all__ = [
    "ARQ_EVENTS_CONTEXT_KEY",
    "ArqEvents",
    "ArqMetricsError",
    "ArqQueueJobEvent",
    "ArqQueueStatsEvent",
    "initialize_arq_metrics",
    "make_on_job_start",
    "publish_queue_stats",
]


ARQ_EVENTS_CONTEXT_KEY = "_arq_events"


class ArqQueueJobEvent(EventPayload):
    """Metrics for every job run by Arq."""

    time_in_queue: timedelta
    """Time between ideal job start and when it actually starts."""

    queue: str
    """The queue the job was picked from."""


class ArqQueueStatsEvent(EventPayload):
    """Statistics for an Arq queue."""

    num_queued: int
    """The number of jobs that are currently in the queue."""

    queue: str
    """The queue that these stats apply to."""


class ArqEvents:
    """Container for Arq metrics event publishers."""

    async def initialize(self, manager: EventManager) -> None:
        """Create publishers for generic Arq events.

        Parameters
        ----------
        manager
            An initialized `safir.metrics.EventManager`
        """
        self.arq_queue_job_event = await manager.create_publisher(
            "arq_job_run", ArqQueueJobEvent
        )

        self.arq_queue_stats = await manager.create_publisher(
            "arq_queue_stats", ArqQueueStatsEvent
        )


async def initialize_arq_metrics(
    event_manager: EventManager, ctx: dict
) -> None:
    """Create Arq metrics publishers and inject them into the Arq context.

    Parameters
    ----------
    event_manager
        And initialized `safir.metrics.EventManager`
    ctx
        The context that gets passed to the on_startup function. This will be
        mutated to add the ArqEvents instance.
    """
    events = ArqEvents()
    await events.initialize(event_manager)
    ctx[ARQ_EVENTS_CONTEXT_KEY] = events


class ArqMetricsError(Exception):
    """An exception from misuse/misconfiguration of Arq app metrics."""


class ArqMetricsContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    events: Annotated[
        ArqEvents, Field(validation_alias=ARQ_EVENTS_CONTEXT_KEY)
    ]
    """An object that contains Arq metrics events."""

    # The score in the job context is the number of milliseconds since the
    # epoch that this job would ideally start executing. Any difference
    # between now (when is when the job actually starts executing) and this
    # score is time waiting in the queue for other jobs to execute.
    #
    # Note there is also an enqueue_time item in the job context, and this
    # is set to the time that the job was placed into the queue. We can't
    # use this for defered jobs and crons becuase the time between then and
    # now includes the time between when the job was enqueued and when we
    # actually want it to run. Score is the time we actually want it to
    # run.
    ideal_start_time: Annotated[datetime, Field(validation_alias="score")]
    """The time that this job should run."""


def make_on_job_start(queue_name: str) -> StartupShutdown:
    """Make a function that publishes an event for every job execution.

    This should be set as, or composed with, your ``on_job_start`` function in
    your Arq ``WorkerSettings`` class. You need to also call
    `safir.metrics.arq.initialize_arq_metrics` in your worker
    ``on_startup`` function.

    Parameters
    ----------
    queue_name
        The name of the queue that this worker will be listening on.
    """

    async def on_job_start(ctx: dict[Any, Any]) -> Any:
        try:
            context = ArqMetricsContext(**ctx)
        except Exception as e:
            msg = (
                "Arq context does not contain expected values. Make sure you "
                "ran initialize_arq_metrics in your worker on_startup "
                "function."
            )
            raise ArqMetricsError(msg) from e

        now = current_datetime(microseconds=True)
        time_in_queue = now - context.ideal_start_time

        event = ArqQueueJobEvent(
            time_in_queue=time_in_queue,
            queue=queue_name,
        )
        await context.events.arq_queue_job_event.publish(event)

    return on_job_start


async def publish_queue_stats(
    queue: str,
    redis_settings: RedisSettings,
    arq_events: ArqEvents,
) -> None:
    """Publish an event containing statistics about an Arq queue.

    Parameters
    ----------
    queue
        The name of the Arq queue.
    redis_settings
        Connection info for the redis instance containing the queue.
    arq_events
        A collection of Arq metrics event publishers.
    """
    redis = await create_pool(redis_settings)
    num_queued = await redis.zcard(queue)
    event = ArqQueueStatsEvent(queue=queue, num_queued=num_queued)
    await arq_events.arq_queue_stats.publish(event)
