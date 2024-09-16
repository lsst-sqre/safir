import inspect
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self, TypeVar

from dataclasses_avroschema.pydantic import AvroBaseModel
from schema_registry.client import AsyncSchemaRegistryClient
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)

from .config import SchemaManagerSettings
from .exceptions import InvalidAvroNameError, UnmanagedSchemaError

P = TypeVar("P", bound=AvroBaseModel)


class DeserializeError(Exception):
    pass


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
    schema: dict[str, Any]
    schema_id: int
    subject: str


class PydanticSchemaManager:
    """A manager for schemas that are represented as Pydantic models in Python,
    and translated into Avro for the Confluent Schema Registry.

    Parameters
    ----------
    registry
        The Registry API client instance.
    suffix
        A suffix that is added to the schema name (and thus subject name), for
        example ``_dev1``.

        The suffix creates alternate subjects in the Schema Registry so
        schemas registered during testing and staging don't affect the
        compatibility continuity of a production subject.

        For production, it's best to not set a suffix.
    """

    @classmethod
    def from_config(cls, config: SchemaManagerSettings) -> Self:
        registry = AsyncSchemaRegistryClient(
            url=str(config.schema_registry.url)
        )
        return cls(registry=registry, suffix=config.suffix)

    def __init__(
        self, *, registry: AsyncSchemaRegistryClient, suffix: str = ""
    ) -> None:
        self._registry = registry
        self._serializer = AsyncAvroMessageSerializer(self._registry)
        self._suffix = suffix

        self._logger = logging.getLogger(__name__)

        # A mapping of subjects to registered schema ids.
        self._models: dict[str, int] = {}

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
        """
        schema = model.avro_schema_to_python()
        subject = self._get_model_fqn(model)
        schema_id = await self._registry.register(subject, schema)
        self._models[subject] = schema_id

        if compatibility is not None:
            await self._registry.update_compatibility(
                subject=subject,
                level=compatibility,
            )

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
        subject = self._get_model_fqn(data)
        try:
            schema_id = self._models[subject]
        except KeyError:
            raise UnmanagedSchemaError(
                f"Schema for model: {data} with subject: {subject} was never"
                " registered. `PydanticSchemaManager.register` must be called"
                " before you try to serialize instances of this model."
            ) from None
        return await self._serializer.encode_record_with_schema_id(
            schema_id, data.model_dump()
        )

    async def deserialize(self, data: bytes, model: type[P]) -> P:
        """Deserialize the data.

        Parameters
        ----------
        data
            The data to deserialize.
        model
            The AvroBaseModel to construct with the deserialized data.

        Returns
        -------
        P
            An instance of the model class passed in the model parameter.
        """
        raw = await self._serializer.decode_message(data)
        if raw is None:
            raise DeserializeError(
                "Could not deserialize for an unkown reason"
            )
        return model(**raw)

    def _get_model_fqn(
        self, model: AvroBaseModel | type[AvroBaseModel]
    ) -> str:
        # Mypy can't detect the Meta class on the model, so we have to ignore
        # those lines.

        klass = model if inspect.isclass(model) else model.__class__

        try:
            name = klass.Meta.schema_name  # type: ignore [union-attr]
        except AttributeError:
            name = klass.__name__

        try:
            namespace = klass.Meta.namespace  # type: ignore [union-attr]
        except AttributeError:
            namespace = None

        if namespace:
            name = f"{namespace}.{name}"

        if self._suffix:
            name += self._suffix

        self._validate_name(name)
        return name

    def _validate_name(self, name: str) -> None:
        pattern = r"^[A-Za-z_][A-Za-z0-9_]*$"

        bad = [part for part in name.split(".") if not re.match(pattern, part)]
        if bad:
            raise InvalidAvroNameError(
                f"{name} has invalid Avro name parts: {bad}. Each part must"
                f"match: {pattern}"
            )
