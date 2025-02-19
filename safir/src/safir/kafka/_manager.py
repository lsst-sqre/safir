"""Manage remote Confluent schema registry schemas via Pydantic models.

Taken from Jonathan Sick's work in Kafkit_, with all
of the hard parts replaced with python-schema-registry-client_.

.. _Kafkit: https://kafkit.lsst.io/
.. _python-schema-registry-client: https://marcosschroh.github.io/python-schema-registry-client/
"""

import inspect
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog
from dataclasses_avroschema.pydantic import AvroBaseModel
from schema_registry.client import AsyncSchemaRegistryClient
from schema_registry.client.errors import ClientError
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)
from structlog.stdlib import BoundLogger

from ._exceptions import (
    IncompatibleSchemaError,
    InvalidAvroNameError,
    UnknownSchemaError,
)

__all__ = [
    "Compatibility",
    "PydanticSchemaManager",
    "SchemaInfo",
]


class Compatibility(StrEnum):
    """Schema registry compatibility types."""

    BACKWARD = "BACKWARD"
    BACKWARD_TRANSITIVE = "BACKWARD_TRANSITIVE"
    FORWARD = "FORWARD"
    FORWARD_TRANSITIVE = "FORWARD_TRANSITIVE"
    FULL = "FULL"
    FULL_TRANSITIVE = "FULL_TRANSITIVE"
    NONE = "NONE"


@dataclass
class SchemaInfo:
    """Schema and registry metadata."""

    schema: dict[str, Any]
    """The Avro schema as a Python dict."""

    schema_id: int
    """The ID of the schema in the schema registry."""

    subject: str
    """The subject that the schema is registered under in the registry."""


class PydanticSchemaManager:
    """A manager for schemas that are represented as Pydantic models in Python,
    and translated into Avro for the Confluent Schema Registry.

    It can be used to:

    * Register new schemas from Pydantic models
    * Register new versions of existing schemas from changed Pydantic models,
      after checking compatibility with the latest version in the registry

    Parameters
    ----------
    registry
        A schema registry client, or connection settings for creating one
    suffix
        A suffix that is added to the schema name (and thus subject name), for
        example ``_dev1``.

        The suffix creates alternate subjects in the Schema Registry so
        schemas registered during testing and staging don't affect the
        compatibility continuity of a production subject.

        For production, it's best to not set a suffix.
    logger
        Logger to use for internal logging. If not given, the
        ``safir.kafka.manager`` logger will be used.
    """

    def __init__(
        self,
        registry: AsyncSchemaRegistryClient,
        suffix: str = "",
        logger: BoundLogger | None = None,
    ) -> None:
        self._registry = registry
        self._serializer = AsyncAvroMessageSerializer(self._registry)
        self._suffix = suffix

        self._logger = logger or structlog.get_logger("safir.kafka.manager")

        # A mapping of subjects to registered schema ids.
        self._subjects_to_ids: dict[str, int] = {}

    async def register_model(
        self,
        model: type[AvroBaseModel],
        compatibility: Compatibility | None = None,
    ) -> SchemaInfo:
        """Register the model with the registry.

        Parameters
        ----------
        model
            The model to register.
        compatibility
            The registry `compatibility type <https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html#compatibility-types>`__
            for this model. If not provided, it will default to the default
            type configured in the registry.

        Raises
        ------
        IncompatibleSchemaError
            If the schema is incompatible with the latest version of schema in
            the registry, according to the subject's compatibility type.
        """
        subject = self._get_subject(model)
        if compatibility:
            await self._registry.update_compatibility(
                subject=subject,
                level=compatibility,
            )

        # If a schema has been successfully registered before, and thus has a
        # version in the registry, trying to create a new version of the schema
        # in the registry will always succeed and return the schema id of the
        # previously registered version, regardless of it's compatibility
        # with the latest version. This can happen when we're trying to "roll
        # back" a schema.
        #
        # In these cases, we want to raise an error if the candidate schema is
        # incompatible. The only way to accomplish this is to explicitly check
        # compatibility with the latest version in the registry.
        #
        # NOTE: This also doesn't update the 'latest' version to the candidate
        # schema after a register call of the candidate schema. "latest"
        # remains at the last registered non-repeat version.
        schema = model.avro_schema_to_python()
        result = await self._registry.test_compatibility(
            subject=subject, schema=schema, verbose=True
        )
        # This is here just to satisfy the type checker. The test_compatibility
        # method returns a bool if verbose == False, and a dict if verbose ==
        # True.
        if not isinstance(result, dict):
            raise TypeError(
                f"test_compatibility returned {type(result).__name__}, not"
                " dict"
            )
        if "is_compatible" not in result:
            raise ValueError(
                "test_compatibility returned a dict without the"
                "'is_compatible' key: {result}"
            )

        if result["is_compatible"] is False:
            raise IncompatibleSchemaError(result["messages"])

        try:
            schema_id = await self._registry.register(subject, schema)
        except ClientError as e:
            self._logger.exception(
                "schema registry ClientError",
                msg=e.message,
                http_code=e.http_code,
                server_traceback=e.server_traceback,
            )
            raise
        self._subjects_to_ids[subject] = schema_id

        return SchemaInfo(schema=schema, schema_id=schema_id, subject=subject)

    async def serialize(self, data: AvroBaseModel) -> bytes:
        """Serialize the data.

        The model's schema must have been registered before calling this
        method.

        Parameters
        ----------
        data
            The data to serialize.

        Returns
        -------
        bytes
            The serialized data in the Confluent Wire Format.
        """
        subject = self._get_subject(data)
        try:
            schema_id = self._subjects_to_ids[subject]
        except KeyError:
            raise UnknownSchemaError(data, subject) from None
        return await self._serializer.encode_record_with_schema_id(
            schema_id, data.model_dump()
        )

    def _get_subject(self, model: AvroBaseModel | type[AvroBaseModel]) -> str:
        """Get a unique subject for this model based on metadata and config."""
        # Mypy can't detect the Meta class on the model, so we have to ignore
        # those lines.

        klass = model if inspect.isclass(model) else model.__class__

        try:
            name = str(klass.Meta.schema_name)  # type: ignore [union-attr]
        except AttributeError:
            name = klass.__name__

        try:
            namespace = str(klass.Meta.namespace)  # type: ignore [union-attr]
        except AttributeError:
            namespace = None

        if namespace:
            name = f"{namespace}.{name}"

        if self._suffix:
            name += self._suffix

        self._validate_avro_name(name)
        return name

    def _validate_avro_name(self, name: str) -> None:
        """Avro record and namespace names are constrained in their format.

        https://avro.apache.org/docs/1.11.1/specification/#names
        """
        pattern = r"^[A-Za-z_][A-Za-z0-9_]*$"

        bad = [part for part in name.split(".") if not re.match(pattern, part)]
        if bad:
            raise InvalidAvroNameError(
                f"{name} has invalid Avro name parts: {bad}. Each part must"
                f"match: {pattern}"
            )
