"""Tests for the schema management functionality in the safir.kafka module."""

from typing import Any

import pytest
from dataclasses_avroschema.pydantic import AvroBaseModel
from pydantic import Field
from schema_registry.client import AsyncSchemaRegistryClient
from schema_registry.serializers.message_serializer import (
    AsyncAvroMessageSerializer,
)

from safir.kafka import (
    Compatibility,
    IncompatibleSchemaError,
    InvalidAvroNameError,
    PydanticSchemaManager,
    SchemaInfo,
    UnknownSchemaError,
)
from safir.kafka._schema_registry_config import SchemaManagerSettings


async def assert_round_trip(
    manager: PydanticSchemaManager,
    model: type[AvroBaseModel],
    settings: SchemaManagerSettings,
    **kwargs: Any,
) -> SchemaInfo:
    info = await manager.register_model(model)
    original = model(**kwargs)
    serialized = await manager.serialize(original)

    # deserialize by getting the schema from the registry
    fresh_registry_client = AsyncSchemaRegistryClient(
        **settings.to_registry_params()
    )
    fresh_serializer = AsyncAvroMessageSerializer(fresh_registry_client)
    raw = await fresh_serializer.decode_message(serialized)
    assert raw is not None
    deserialized = model(**raw)
    assert deserialized == original
    return info


@pytest.mark.asyncio
async def test_no_metadata(
    schema_manager: PydanticSchemaManager,
    schema_manager_settings: SchemaManagerSettings,
) -> None:
    class MyBareModel(AvroBaseModel):
        str_field: str
        int_field: int

    info = await assert_round_trip(
        schema_manager,
        MyBareModel,
        schema_manager_settings,
        str_field="blah",
        int_field=123,
    )
    assert info.subject == "MyBareModel"
    assert info.schema["name"] == "MyBareModel"
    assert info.schema.get("namespace", None) is None


@pytest.mark.asyncio
async def test_name_only_metadata(
    schema_manager: PydanticSchemaManager,
    schema_manager_settings: SchemaManagerSettings,
) -> None:
    class MyModel(AvroBaseModel):
        str_field: str
        int_field: int

        class Meta:
            schema_name = "mymodelcustom"

    info = await assert_round_trip(
        schema_manager,
        MyModel,
        schema_manager_settings,
        str_field="blah",
        int_field=123,
    )
    assert info.subject == "mymodelcustom"
    assert info.schema["name"] == "mymodelcustom"
    assert info.schema.get("namespace", None) is None


@pytest.mark.asyncio
async def test_name_and_namespace_metadata(
    schema_manager: PydanticSchemaManager,
    schema_manager_settings: SchemaManagerSettings,
) -> None:
    class MyOtherModel(AvroBaseModel):
        str_field: str
        int_field: int

        class Meta:
            schema_name = "myothermodelcustom"
            namespace = "my.other.namespace"

    info = await assert_round_trip(
        schema_manager,
        MyOtherModel,
        schema_manager_settings,
        str_field="blah",
        int_field=123,
    )
    assert info.subject == "my.other.namespace.myothermodelcustom"
    assert info.schema["name"] == "myothermodelcustom"
    assert info.schema["namespace"] == "my.other.namespace"


@pytest.mark.asyncio
async def test_namespace_only_metadata(
    schema_manager: PydanticSchemaManager,
    schema_manager_settings: SchemaManagerSettings,
) -> None:
    class YetAnotherModel(AvroBaseModel):
        str_field: str
        int_field: int

        class Meta:
            namespace = "yetanothernamespace"

    info = await assert_round_trip(
        schema_manager,
        YetAnotherModel,
        schema_manager_settings,
        str_field="blah",
        int_field=123,
    )
    assert info.subject == "yetanothernamespace.YetAnotherModel"
    assert info.schema["name"] == "YetAnotherModel"
    assert info.schema["namespace"] == "yetanothernamespace"


@pytest.mark.asyncio
async def test_suffix(
    schema_manager_settings: SchemaManagerSettings,
) -> None:
    registry = AsyncSchemaRegistryClient(
        **schema_manager_settings.to_registry_params()
    )
    schema_manager = PydanticSchemaManager(
        registry=registry,
        suffix="_test_suffix",
    )

    class MyModel(AvroBaseModel):
        str_field: str
        int_field: int

        class Meta:
            schema_name = "mymodel"
            namespace = "my.namespace"

    info = await assert_round_trip(
        schema_manager,
        MyModel,
        schema_manager_settings,
        str_field="blah",
        int_field=123,
    )
    assert info.subject == "my.namespace.mymodel_test_suffix"
    assert info.schema["name"] == "mymodel"
    assert info.schema["namespace"] == "my.namespace"


@pytest.mark.asyncio
async def test_invalid_name(
    schema_manager: PydanticSchemaManager,
) -> None:
    class YouGiveLove(AvroBaseModel):
        str_field: str
        int_field: int

        class Meta:
            schema_name = "a-bad-name"

    with pytest.raises(InvalidAvroNameError):
        await schema_manager.register_model(YouGiveLove)


@pytest.mark.asyncio
async def test_forward_compatibility(
    schema_manager: PydanticSchemaManager,
) -> None:
    class MyForwardModel(AvroBaseModel):
        field1: str
        field2: str

    await schema_manager.register_model(
        MyForwardModel, compatibility=Compatibility.FORWARD
    )

    # Adding a field is forward compatible
    class MyForwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str
        field3: str

    await schema_manager.register_model(MyForwardModel)

    # Adding another field is forward compatible
    class MyForwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str
        field3: str
        field4: str

    await schema_manager.register_model(MyForwardModel)

    # Removing a field without a default is NOT foward compatible, even if
    # there is an identical grandparent or older schema.
    class MyForwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str
        field3: str

    with pytest.raises(
        IncompatibleSchemaError, match=r"READER_FIELD_MISSING_DEFAULT_VALUE"
    ):
        await schema_manager.register_model(MyForwardModel)

    # Giving a field a default is forward compatible
    class MyForwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str
        field3: str
        field4: str = Field(default="blah")

    await schema_manager.register_model(MyForwardModel)

    # Removing a field with a default is foward compatible
    class MyForwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str
        field3: str

    await schema_manager.register_model(MyForwardModel)

    # Adding new fields is forward compatible
    class MyForwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str
        field3: str
        field4: str
        field5: str

    await schema_manager.register_model(MyForwardModel)


@pytest.mark.asyncio
async def test_backward_compatibility(
    schema_manager: PydanticSchemaManager,
) -> None:
    class MyBackwardModel(AvroBaseModel):
        field1: str
        field2: str

    await schema_manager.register_model(
        MyBackwardModel, compatibility=Compatibility.BACKWARD
    )

    # Removing fields is backwards compatible
    class MyBackwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str

    await schema_manager.register_model(MyBackwardModel)

    # Adding fields is NOT backwards compatible, even if an identical schema
    # has been previously registered
    class MyBackwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str

    with pytest.raises(
        IncompatibleSchemaError, match=r"READER_FIELD_MISSING_DEFAULT_VALUE"
    ):
        await schema_manager.register_model(MyBackwardModel)

    # Adding a field with a default value is backwards compatible
    class MyBackwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str = Field(default="blah")

    await schema_manager.register_model(MyBackwardModel)

    # Removing a default value is backwards compatible
    class MyBackwardModel(AvroBaseModel):  # type: ignore[no-redef]
        field1: str
        field2: str

    await schema_manager.register_model(MyBackwardModel)


@pytest.mark.asyncio
async def test_unmanaged_error(
    schema_manager: PydanticSchemaManager,
) -> None:
    class MyModel(AvroBaseModel):
        str_field: str
        int_field: int

        class Meta:
            namespace = "what.ever"

    original = MyModel(str_field="somestring", int_field=123)

    with pytest.raises(
        UnknownSchemaError,
        match="model: MyModel with subject: what.ever.MyModel",
    ):
        await schema_manager.serialize(original)
