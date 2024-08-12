"""An asyncio multiple reader, multiple writer queue."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from types import EllipsisType
from typing import Generic, TypeVar

from safir.datetime import current_datetime

#: Type variable of objects being stored in `AsyncMultiQueue`.
T = TypeVar("T")

__all__ = [
    "AsyncMultiQueue",
    "AsyncMultiQueueError",
    "T",
]


class AsyncMultiQueueError(Exception):
    """Invalid sequence of calls when writing to `AsyncMultiQueue`."""


class AsyncMultiQueue(Generic[T]):
    """An asyncio multiple reader, multiple writer queue.

    Provides a generic queue for asyncio that supports multiple readers (via
    async iterator) and multiple writers. Readers can start reading at any
    time and will begin reading from the start of the queue. There is no
    maximum size of the queue; new items will be added subject only to the
    limits of available memory.

    This data structure is not thread-safe. It uses only asyncio locking, not
    thread-safe locking.

    The ellipsis object (``...``) is used as a placeholder to indicate the end
    of the queue, so cannot be pushed onto the queue.
    """

    def __init__(self) -> None:
        self._contents: list[T | EllipsisType] = []
        self._triggers: list[asyncio.Event] = []

    def __aiter__(self) -> AsyncIterator[T]:
        """Return an async iterator over the queue."""
        return self.aiter_from(0)

    @property
    def finished(self) -> bool:
        """Whether `close` has been called on the queue.

        If this property is `True`, the contents of the queue are finalized
        and no new items will be added unless the queue is cleared with
        `clear`.
        """
        return bool(self._contents and self._contents[-1] is Ellipsis)

    def aiter_from(
        self, start: int, timeout: timedelta | None = None
    ) -> AsyncIterator[T]:
        """Return an async iterator over the queue.

        Each call to this function returns a separate iterator over the same
        underlying contents, and each iterator will be triggered separately.

        Parameters
        ----------
        start
            Starting position in the queue. This can be larger than the
            current queue size, in which case no items are returned until the
            queue passes the given starting position.
        timeout
            If given, total length of time for the iterator. This isn't the
            timeout waiting for the next item; this is the total execution
            time of the iterator.

        Returns
        -------
        AsyncIterator
            An async iterator over the contents of the queue.

        Raises
        ------
        TimeoutError
            Raised when the timeout is reached.
        """
        if timeout:
            end_time = current_datetime(microseconds=True) + timeout
        else:
            end_time = None

        # Grab a reference to the current contents so that the iterator
        # detaches from the contents on clear.
        contents = self._contents

        # Add a trigger for this caller.
        trigger = asyncio.Event()
        self._triggers.append(trigger)

        # Construct the iterator, which waits for the trigger and returns any
        # new events until it sees the placeholder for the end of the queue
        # (the ellipsis object).
        async def iterator() -> AsyncIterator[T]:
            position = start
            try:
                while True:
                    trigger.clear()
                    end = len(contents)
                    if position < end:
                        for item in contents[position:end]:
                            if item is Ellipsis:
                                return
                            yield item
                        position = end
                    elif contents and contents[-1] is Ellipsis:
                        return
                    if end_time:
                        now = current_datetime(microseconds=True)
                        timeout_left = (end_time - now).total_seconds()
                        async with asyncio.timeout(timeout_left):
                            await trigger.wait()
                    else:
                        await trigger.wait()
            finally:
                self._triggers = [t for t in self._triggers if t != trigger]

        return iterator()

    def clear(self) -> None:
        """Empty the contents of the queue.

        Any existing readers will still see all items pushed to the queue
        before the clear, but will become detached from the queue and will not
        see any new events added after the clear.
        """
        finished = self.finished
        contents = self._contents
        triggers = self._triggers
        self._contents = []
        self._triggers = []
        if not finished:
            contents.append(Ellipsis)
            for trigger in triggers:
                trigger.set()

    def close(self) -> None:
        """Mark the end of the queue data.

        Similar to `clear` in that any existing readers of the queue will see
        the end of the iterator, but the data will not be deleted and new
        readers can still read all of the data in the queue.

        After `close` is called, `clear` must be called before any subsequent
        `put`.
        """
        self._contents.append(Ellipsis)
        for trigger in self._triggers:
            trigger.set()

    def put(self, item: T) -> None:
        """Add an item to the queue.

        Parameters
        ----------
        item
           Item to add.

        Raises
        ------
        AsyncMultiQueueError
            Raised if `put` was called after `close` without an intervening
            call to `clear`.
        """
        if self.finished:
            msg = "end was already called, must call clear before put"
            raise AsyncMultiQueueError(msg)
        self._contents.append(item)
        for trigger in self._triggers:
            trigger.set()

    def qsize(self) -> int:
        """Return the number of items currently in the queue."""
        count = len(self._contents)
        if self.finished:
            count -= 1
        return count
