"""Tests for asyncio utility functions."""

from __future__ import annotations

import asyncio

import pytest

from safir.asyncio import (
    AsyncMultiQueue,
    AsyncMultiQueueError,
    run_with_asyncio,
)


@pytest.mark.asyncio
async def test_async_multi_queue() -> None:
    queue = AsyncMultiQueue[str]()
    queue.put("one")
    queue.put("two")
    assert queue.qsize() == 2

    # Here and below, use this somewhat awkward construction to hide the
    # assertion from mypy's type narrowing of class attributes.
    finished = queue.finished
    assert not finished

    async def watcher(position: int) -> list[str]:
        return [s async for s in queue.aiter_from(position)]

    async def watcher_iter() -> list[str]:
        return [s async for s in queue]

    start_task = asyncio.create_task(watcher_iter())
    one_task = asyncio.create_task(watcher(1))
    current_task = asyncio.create_task(watcher(queue.qsize()))
    future_task = asyncio.create_task(watcher(3))
    way_future_task = asyncio.create_task(watcher(10))

    await asyncio.sleep(0.1)
    queue.put("three")
    await asyncio.sleep(0.1)
    queue.put("four")
    await asyncio.sleep(0.1)
    queue.clear()
    assert queue.qsize() == 0
    finished = queue.finished
    assert not finished

    after_clear_task = asyncio.create_task(watcher_iter())
    await asyncio.sleep(0.1)
    queue.put("something")
    queue.close()
    assert queue.finished
    assert queue.qsize() == 1

    assert await start_task == ["one", "two", "three", "four"]
    assert await one_task == ["two", "three", "four"]
    assert await current_task == ["three", "four"]
    assert await future_task == ["four"]
    assert await way_future_task == []
    assert await after_clear_task == ["something"]

    with pytest.raises(AsyncMultiQueueError):
        queue.put("else")


def test_run_with_asyncio() -> None:
    @run_with_asyncio
    async def some_async_function() -> str:
        return "some result"

    assert some_async_function() == "some result"
