### Backwards-incompatible changes

- `EventDuration` has been removed from `safir.metrics`. You can now use Python's built-in `timedelta` as the type for any field you were previously using `EventDuration`. It will be serialized the same way, as an Avro `double` number of seconds.
