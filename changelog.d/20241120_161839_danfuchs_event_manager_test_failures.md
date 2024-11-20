### New features

- `safir.kafka.PydanticSchemaManager` takes an optional structlog `BoundLogger`. If not provided, the default logger is a `BoundLogger`, rather than a `logging.Logger`.
- `logger` value to `safir.metrics.KafkaMetricsConfiguration.make_manager` is passed through to the `PydanticSchemaManager` instance that it creates.
