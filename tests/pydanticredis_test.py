"""Tests for the safir.pydanticredis module."""

from __future__ import annotations

import pytest
import redis.asyncio as redis
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field

from safir.pydanticredis import (
    EncryptedPydanticRedisStorage,
    PydanticRedisStorage,
)


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
