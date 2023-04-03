"""Tests for the safir.redis module."""

from __future__ import annotations

import pytest
import redis.asyncio as redis
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field

from safir.redis import EncryptedPydanticRedisStorage, PydanticRedisStorage


class DemoModel(BaseModel):
    """A demo model for testing."""

    name: str = Field(..., description="The name of the model.")
    value: int = Field(..., description="The value of the model.")


async def basic_testing(storage: PydanticRedisStorage[DemoModel]) -> None:
    """Test basic storage operations for either encrypted or unencrypted
    storage.
    """
    await storage.store("mark42", DemoModel(name="Mark", value=42))
    await storage.store("mark13", DemoModel(name="Mark", value=13))
    await storage.store("jon7", DemoModel(name="Jon", value=7))

    assert await storage.get("mark42") == DemoModel(name="Mark", value=42)
    async for key in storage.scan("mark*"):
        assert key in ["mark13", "mark42"]

    assert await storage.delete("mark42") is True
    assert [m async for m in storage.scan("mark*")] == ["mark13"]
    assert await storage.get("mark42") is None
    assert await storage.delete("mark42") is False

    await storage.delete_all("mark*")
    assert [m async for m in storage.scan("mark*")] == []

    await storage.delete_all("*")
    assert await storage.get("jon7") is None


@pytest.mark.asyncio
async def test_pydantic_redis_storage(redis_client: redis.Redis) -> None:
    """Test unencrypted storage with the DemoModel."""
    storage = PydanticRedisStorage(datatype=DemoModel, redis=redis_client)
    await basic_testing(storage)


@pytest.mark.asyncio
async def test_pydantic_redis_storage_with_prefix(
    redis_client: redis.Redis,
) -> None:
    """Test unencrypted storage with the DemoModel."""
    storage = PydanticRedisStorage(
        datatype=DemoModel, redis=redis_client, key_prefix="test:"
    )
    await basic_testing(storage)


@pytest.mark.asyncio
async def test_encrypted_pydantic_redis_storage(
    redis_client: redis.Redis,
) -> None:
    """Test encrypted storage."""
    storage = EncryptedPydanticRedisStorage(
        datatype=DemoModel,
        redis=redis_client,
        encryption_key=Fernet.generate_key().decode(),
    )
    await basic_testing(storage)


class PetModel(BaseModel):
    id: int
    name: str
    age: int


class CustomerModel(BaseModel):
    id: int
    name: str
    email: str


@pytest.mark.asyncio
async def test_multiple_stores(redis_client: redis.Redis) -> None:
    """Test multiple stores with unique prefixes for each."""
    pet_store = PydanticRedisStorage(
        datatype=PetModel,
        redis=redis_client,
        key_prefix="pet:",
    )
    customer_store = PydanticRedisStorage(
        datatype=CustomerModel,
        redis=redis_client,
        key_prefix="customer:",
    )

    await pet_store.store("emma", PetModel(id=1, name="Emma", age=2))
    await customer_store.store(
        "emma", CustomerModel(id=1, name="Emma", email="emma@example.com")
    )

    assert await pet_store.get("emma") == PetModel(id=1, name="Emma", age=2)
    assert await customer_store.get("emma") == CustomerModel(
        id=1, name="Emma", email="emma@example.com"
    )

    # Scanned keys should not contain the prefix.
    assert [m async for m in pet_store.scan("*")] == ["emma"]
    assert [m async for m in customer_store.scan("*")] == ["emma"]

    await pet_store.delete_all("*")
    # Pet emma should be gone, but customer emma should still be there.
    assert await pet_store.delete("emma") is False
    assert await customer_store.delete("emma") is True
