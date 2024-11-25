"""Dependencies for metrics functionality."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from safir.metrics import EventManager

__all__ = ["E", "EventDependency", "EventMaker"]

E = TypeVar("E", bound="EventMaker")
"""Generic event maker type."""


class EventMaker(ABC):
    """A blueprint for an event publisher container class."""

    @abstractmethod
    async def initialize(self, manager: EventManager) -> None:
        """Create event publishers and assign to instance attributes.

        Use ``manager.create_publisher`` to assign event publishers to
        instance attributes.

        Parameters
        ----------
        manager
            An ``EventManager`` to create event publishers
        """


class EventDependency(Generic[E]):
    """Provides EventManager-managed events for apps to publish.

    Parameters
    ----------
    event_maker
        An instance of an implementation of ``EventMaker``

    Examples
    --------
    .. code-block:: python
       :caption: myapp.dependencies.events_dependency

       from safir.metrics import (
           EventMaker,
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


       class Events(EventMaker):
           async def initialize(self, manager: EventManager) -> None:
               self.event1 = await manager.create_publisher("event1", Event1)
               self.event2 = await manager.create_publisher("event2", Event2)


       dependency = EventsDependency(AppEvents())

    .. code-block:: python
       :caption: myapp.main

       from myapp.dependencies.events_dependency import dependency as ed

       # In application init, maybe a lifecycle method in a FastAPI app
       manager = MetricsConfigurationWithKafka().make_manager()
       await manager.initialize()
       await events.initialize(manager)

    .. code-block:: python
       :caption: myapp.someservice

       from myapp.dependencies.events_dependency import dependency as ed


       events = ed()

       # In app code
       await events.event1.publish(Event1(foo="foo", bar="bar"))
       await events.event2.publish(Event2(baz=123, buz="buz"))
    """

    def __init__(self, event_maker: E) -> None:
        self._events = event_maker
        self._initialized = False

    async def initialize(
        self,
        manager: EventManager,
    ) -> None:
        """Initialize the event maker and set the attribute.

        Parameters
        ----------
        manager
            An ``EventManager`` to register and publish events.
        """
        await self._events.initialize(manager)
        self._initialized = True

    @property
    def events(self) -> E:
        """Return the instantiated event maker.

        Raises
        ------
        RuntimeError
            If this ``EventsDependency`` hasn't been intialized yet.
        """
        if not self._initialized:
            raise RuntimeError("EventsDependency not initialized")
        return self._events

    async def __call__(self) -> E:
        """Return the initialized event maker for use as a FastAPI
        dependency.
        """
        return self.events
