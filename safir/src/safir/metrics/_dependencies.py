from collections.abc import Callable
from typing import Generic, TypeVar

from ._event_manager import EventManager

__all__ = ["EventDependency"]

E = TypeVar("E")
"""Generic event maker type."""


class EventDependency(Generic[E]):
    """Provides EventManager-managed events for apps to publish.

    .. code-block:: python
       :caption: myapp.dependencies.events_dependency

       from safir.metrics import (
           EventManager,
           EventPayload,
           EventsDependency,
           MetricsConfigurationWithKafka,
       )


       class Event1(EventPayload):
           foo: str
           bar: str


       class event2(EventPayload):
           baz: int
           buz: str


       class AppEvents:
           def __init__(self, manager: EventManager) -> None:
               self.event1 = manager.create_publisher("event1", Event1)
               self.event2 = manager.create_publisher("event2", Event2)


       dependency = EventsDependency(AppEvents)

    .. code-block:: python
       :caption: myapp.main

       from myapp.dependencies.events_dependency import dependency as ed

       # In application init, maybe a lifecycle method in a FastAPI app
       manager = MetricsConfigurationWithKafka().make_manager()
       await events.initialize(manager)

    .. code-block:: python
       :caption: myapp.someservice

       from myapp.dependencies.events_dependency import dependency as ed


       events = ed()

       # In app code
       events.event1.publish(Event1(foo="foo", bar="bar"))
       events.event2.publish(Event2(baz=123, buz="buz"))

    Parameters
    ----------
    event_maker
        A callable that takes and ``EventManager``. This callable is expected
        to register events with the event manager when called. It is probably
        a class that calls ``EventManager.create_publisher`` and assigns the
        results to instance variables.
    """

    def __init__(self, event_maker: Callable[[EventManager], E]) -> None:
        self._events: E | None = None
        self._event_maker = event_maker
        self._manager: EventManager

    async def initialize(
        self,
        *,
        manager: EventManager,
    ) -> None:
        """Construct the event maker callable with the passed in ``manager``.

        Parameters
        ----------
        manager
            An ``EventManager`` to register and publish events.
        """
        self._events = self._event_maker(manager)
        self._manager = manager
        await manager.register_and_initialize()

    @property
    def events(self) -> E:
        """Return the instantiated event maker.

        Raises
        ------
        RuntimeError
            If this ``EventsDependency`` hasn't been intialized yet.
        """
        if not self._events:
            raise RuntimeError("EventsDependency not initialized")
        return self._events

    async def __call__(self) -> E:
        """Return the instantiated event maker for use as a FastAPI
        dependency.
        """
        return self.events

    async def aclose(self) -> None:
        """Clean up the ``EventManager``."""
        await self._manager.aclose()
