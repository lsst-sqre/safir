"""Tools for collecting generic metrics for Arq jobs and queues."""

import functools
from collections.abc import Callable, Coroutine
from datetime import timedelta
from time import time
from typing import cast

from ._event_manager import EventManager
from ._models import EventPayload

__all__ = [
    "ArqEvents",
    "ArqJobRunEvent",
    "ArqMetricsError",
    "initialize_arq_metrics",
    "with_arq_metrics",
]


class ArqJobRunEvent(EventPayload):
    """Metrics for every job run by Arq."""

    time_in_queue: timedelta
    queue: str
    function: str


class ArqEvents:
    """Container for Arq metrics event publishers."""

    async def initialize(self, manager: EventManager) -> None:
        self.arq_job_run = await manager.create_publisher(
            "arq_job_run", ArqJobRunEvent
        )


async def initialize_arq_metrics(
    event_manager: EventManager, ctx: dict
) -> None:
    """Create Arq metrics publishers and inject them into the Arq context."""
    arq_events = ArqEvents()
    await arq_events.initialize(event_manager)
    ctx["_arq_events"] = arq_events


class ArqMetricsError(Exception):
    """An exception from misuse/misconfiguration of Arq app metrics."""


def with_arq_metrics[**P, R](
    func: Callable[P, Coroutine[None, None, R]],
) -> Callable[P, Coroutine[None, None, R]]:
    """Decorate a function to emit metrics events every time Arq runs this job.

    Job functions decorated with this method must be enqueued with
    `safir.arq.ArqQueue.enqueue_job` with an ArqQueue that has been initialized
    with ``metrics_support=True``.
    """

    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            function_name = func.__name__

            queue_name = kwargs.pop("_app_metrics_queue_name")
            queue_name = cast("str", queue_name)

            ctx = args[0]
            ctx = cast("dict", ctx)

            arq_events = ctx["_arq_events"]
            arq_events = cast("ArqEvents", arq_events)

            score = ctx["score"]
            score = cast("int", score)
        except Exception as e:
            msg = (
                "Arq context does not contain expected values. Make sure you: "
                "ran initialize_arq_metrics in your worker startup function, "
                "enqueued the job with `safir.arq.ArqQueue.enqueue_task`, and "
                "passed metrics_support=True when you initialized your "
                "ArqQueue."
            )
            raise ArqMetricsError(msg) from e

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
        start_ms = time() * 1000
        seconds_in_queue = (start_ms - score) / 1000
        time_in_queue = timedelta(seconds=seconds_in_queue)

        event = ArqJobRunEvent(
            time_in_queue=time_in_queue,
            queue=queue_name,
            function=function_name,
        )
        await arq_events.arq_job_run.publish(event)
        return await func(*args, **kwargs)

    # functools.wraps injects Anys into the wrapped function definition for
    # reasons I don't quite understand, and it changes the return type to
    # _Wrapped:
    # https://github.com/python/mypy/issues/17171
    # https://github.com/python/mypy/issues/18204
    #
    # The fix here is to mutate the wrapped function just like functools.wraps
    # does, but to mutably sneak it past mypy:
    # https://github.com/python/mypy/issues/18204#issuecomment-3004743810
    functools.update_wrapper(
        wrapper=wrapper,
        wrapped=func,
    )

    return wrapper
