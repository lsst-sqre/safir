### New features

- Publishing a metrics event no longer waits on confirmation of message delivery to Kafka. This makes publishing much more performant. All events will still be delivered as long as an app awaits `EventManager.aclose` in its lifecycle.
