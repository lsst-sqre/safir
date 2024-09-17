"""Tests for the safir.schema_manager module."""

from typing import Any

import pytest
from dataclasses_avroschema.pydantic import AvroBaseModel
from pydantic import Field
from schema_registry.client.errors import ClientError

from safir.schema_manager.config import (
    SchemaManagerSettings,
    SchemaRegistryConnectionSettings,
)
from safir.schema_manager.exceptions import (
    InvalidAvroNameError,
    UnmanagedSchemaError,
)
from safir.schema_manager.pydantic_schema_manager import (
    Compatibility,
    PydanticSchemaManager,
    SchemaInfo,
)


async def assert_round_trip(
    manager: PydanticSchemaManager,
    model: type[AvroBaseModel],
    **kwargs: Any,
) -> SchemaInfo:
    info = await manager.register_model(model)
    original = model(**kwargs)
    serialized = await manager.serialize(original)
    deserialized = await manager.deserialize(data=serialized, model=model)
    assert deserialized == original
    return info


@pytest.mark.asyncio
async def test_different_metadata(
    schema_manager: PydanticSchemaManager,
) -> None:
    class MyBareModel(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

    info = await assert_round_trip(
        schema_manager, MyBareModel, str_field="blah", int_field=123
    )
    assert info.subject == "MyBareModel"
    assert info.schema["name"] == "MyBareModel"
    assert info.schema.get("namespace", None) is None

    class MyModel(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

        class Meta:
            schema_name = "mymodelcustom"

    info = await assert_round_trip(
        schema_manager, MyModel, str_field="blah", int_field=123
    )
    assert info.subject == "mymodelcustom"
    assert info.schema["name"] == "mymodelcustom"
    assert info.schema.get("namespace", None) is None

    class MyOtherModel(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

        class Meta:
            schema_name = "myothermodelcustom"
            namespace = "my.other.namespace"

    info = await assert_round_trip(
        schema_manager, MyOtherModel, str_field="blah", int_field=123
    )
    assert info.subject == "my.other.namespace.myothermodelcustom"
    assert info.schema["name"] == "myothermodelcustom"
    assert info.schema["namespace"] == "my.other.namespace"

    class YetAnotherModel(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

        class Meta:
            namespace = "yetanothernamespace"

    info = await assert_round_trip(
        schema_manager, YetAnotherModel, str_field="blah", int_field=123
    )
    assert info.subject == "yetanothernamespace.YetAnotherModel"
    assert info.schema["name"] == "YetAnotherModel"
    assert info.schema["namespace"] == "yetanothernamespace"


@pytest.mark.asyncio
async def test_suffix(
    schema_registry_connection_settings: SchemaRegistryConnectionSettings,
) -> None:
    schema_manager = PydanticSchemaManager.from_config(
        SchemaManagerSettings(
            schema_registry=schema_registry_connection_settings,
            suffix="_test_suffix",
        )
    )

    class MyModel(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

        class Meta:
            schema_name = "mymodel"
            namespace = "my.namespace"

    info = await assert_round_trip(
        schema_manager, MyModel, str_field="blah", int_field=123
    )
    assert info.subject == "my.namespace.mymodel_test_suffix"
    assert info.schema["name"] == "mymodel"
    assert info.schema["namespace"] == "my.namespace"


@pytest.mark.asyncio
async def test_invalid_name(
    schema_manager: PydanticSchemaManager,
) -> None:
    class YouGiveLove(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

        class Meta:
            schema_name = "a-bad-name"

    with pytest.raises(InvalidAvroNameError):
        await schema_manager.register_model(YouGiveLove)


@pytest.mark.asyncio
async def test_sets_compatibility(
    schema_manager: PydanticSchemaManager,
) -> None:
    # Forward compatibility
    class MyForwardModel(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

    await schema_manager.register_model(
        MyForwardModel, compatibility=Compatibility.FORWARD
    )

    class MyForwardModel(AvroBaseModel):  # type: ignore[no-redef]
        str_field: str = Field()
        int_field: int = Field()
        bool_field: bool = Field()

    await schema_manager.register_model(MyForwardModel)

    class MyForwardModel(AvroBaseModel):  # type: ignore[no-redef]
        str_field: str = Field()

    with pytest.raises(ClientError, match=r"Incompatible Avro schema"):
        await schema_manager.register_model(MyForwardModel)

    # Backward compatibility
    class MyBackwardModel(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

    await schema_manager.register_model(
        MyBackwardModel, compatibility=Compatibility.BACKWARD
    )

    class MyBackwardModel(AvroBaseModel):  # type: ignore[no-redef]
        str_field: str = Field()

    await schema_manager.register_model(MyBackwardModel)

    class MyBackwardModel(AvroBaseModel):  # type: ignore[no-redef]
        str_field: str = Field()
        int_field: int = Field()
        bool_field: bool = Field()

    with pytest.raises(ClientError, match=r"Incompatible Avro schema"):
        await schema_manager.register_model(MyBackwardModel)


@pytest.mark.asyncio
async def test_unmanaged_error(
    schema_manager: PydanticSchemaManager,
) -> None:
    class MyModel(AvroBaseModel):
        str_field: str = Field()
        int_field: int = Field()

    original = MyModel(str_field="somestring", int_field=123)

    with pytest.raises(UnmanagedSchemaError):
        await schema_manager.serialize(original)
