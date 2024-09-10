import logging
from enum import StrEnum, auto

from dataclasses_avroschema.pydantic import AvroBaseModel
from schema_registry.client import AsyncSchemaRegistryClient
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)


class Compatibility(StrEnum):
    """Schema registry compatibility types."""

    BACKWARD = auto()
    BACKWARD_TRANSITIVE = auto()
    FORWARD = auto()
    FORWARD_TRANSITIVE = auto()
    FULL = auto()
    FULL_TRANSITIVE = auto()
    NONE = auto()


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
    ) -> None:
        """Register the model with the registry.

        Parameters
        ----------
        model
            The model to register.
        """
        schema = model.avro_schema()
        subject = self._get_model_fqn(model)
        schema_id = await self._registry.register(subject, schema)
        self._models[subject] = schema_id

        if compatibility is not None:
            await self._registry.update_compatibility(
                subject=subject,
                level=compatibility,
            )

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
            raise RuntimeError(
                f"Schema for model: {data} with subject: {subject} was never registered. `PydanticSchemaManager.register` must be called before you try to serialize instances of this model."
            ) from None
        return await self._serializer.encode_record_with_schema_id(
            schema_id, data.model_dump()
        )

    def _get_model_fqn(
        self, model: AvroBaseModel | type[AvroBaseModel]
    ) -> str:
        # Mypy can't detect the Meta class on the model, so we have to ignore
        # those lines.

        try:
            name = model.Meta.schema_name  # type: ignore [union-attr]
        except AttributeError:
            name = model.__class__.__name__

        try:
            namespace = model.Meta.namespace  # type: ignore [union-attr]
        except AttributeError:
            namespace = None

        if namespace:
            name = f"{namespace}.{name}"

        if self._suffix:
            name += self._suffix

        return name
