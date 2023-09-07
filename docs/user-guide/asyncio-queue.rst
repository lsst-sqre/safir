#######################################
Using the asyncio multiple-reader queue
#######################################

`~asyncio.Queue`, provided by the basic library, is an asyncio queue implementation, but the protocol it implements delivers each item in the queue to only one reader.
In some cases, you may need behavior more like a publish/subscribe queue: multiple readers all see the full contents of the queue, independently.

Safir provides the `~safir.asyncio.AsyncMultiQueue` data structure for this use case.
Its API is somewhat inspired by that of `~asyncio.Queue`, but it is intended for use as an async iterator rather than by calling a ``get`` method.

The writer should use the queue as follows:

.. code-block:: python

   from safir.asyncio import AsyncMultiQueue


   queue = AsyncMultiQueue[str]()
   queue.put("soemthing")
   queue.put("else")
   queue.close()

Once `~safir.asyncio.AsyncMultiQueue.close` is called, no more data can be added to the queue, and the iterators for all readers will stop when they reach the point where `~safir.asyncio.AsyncMultiQueue.close` was called.

To reset the queue entirely, use `~safir.asyncio.AsyncMultiQueue.clear`.

.. code-block:: python

   queue.clear()

This does the same thing as `~safir.asyncio.AsyncMultiQueue.close` for all existing readers, and then empties the queue and resets it so that new data can be added.
New readers will see a fresh, empty queue.

The type information for `~safir.asyncio.AsyncMultiQueue` can be any type.
Note that the writer interface is fully synchronous.

A typical reader looks like this:

.. code-block:: python

   async for item in queue:
       await do_something(item)

This iterates over the full contents of the queue until `~safir.asyncio.AsyncMultiQueue.close` or `~safir.asyncio.AsyncMultiQueue.clear` is called by the writer.

Readers can also start at any position and specify a timeout.
The timeout, if given, is the total length of time the iterator is allowed to run, not the time to wait for the next element.

.. code-block:: python

   from datetime import timedelta


   timeout = timedelta(seconds=5)
   async for item in queue.aiter_from(4, timeout):
       await do_something(item)

This reader will ignore all elements until the fourth, and will raise `TimeoutError` after five seconds of total time in the iterator.
