"""Storage for Pydantic models in Redis."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Generic, Optional, TypeVar

import redis.asyncio as redis
from cryptography.fernet import Fernet
from pydantic import BaseModel

__all__ = [
    "PydanticRedisStorage",
    "EncryptedPydanticRedisStorage",
    "S",
    "DeserializeError",
]


class DeserializeError(Exception):
    """Raised when a stored object cannot be decrypted or deserialized."""


#: Type variable for the type of object being stored.
S = TypeVar("S", bound="BaseModel")


class PydanticRedisStorage(Generic[S]):
    """JSON-serialized encrypted storage in Redis.

    Parameters
    ----------
    datatype
        The class of object being stored (a Pydantic model).
    redis
        A Redis client configured to talk to the backend store.
    """

    def __init__(self, *, datatype: type[S], redis: redis.Redis) -> None:
        self._datatype = datatype
        self._redis = redis

    async def delete(self, key: str) -> bool:
        """Delete a stored object.

        Parameters
        ----------
        key
            The key to delete.

        Returns
        -------
        bool
            `True` if the key was found and deleted, `False` otherwise.
        """
        count = await self._redis.delete(key)
        return count > 0

    async def delete_all(self, pattern: str) -> None:
        """Delete all stored objects.

        Parameters
        ----------
        pattern
            Glob pattern matching the keys to purge, such as ``oidc:*``.
        """
        async for key in self._redis.scan_iter(pattern):
            await self._redis.delete(key)

    async def get(self, key: str) -> S | None:
        """Retrieve a stored object.

        Parameters
        ----------
        key
            The key for the object.

        Returns
        -------
        Any or None
            The deserialized object or `None` if no such object could be
            found.

        Raises
        ------
        DeserializeError
            Raised if the stored object could not be decrypted or
            deserialized.
        """
        data = await self._redis.get(key)
        if not data:
            return None

        try:
            return self._deserialize(data)
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)}"
            msg = f"Cannot deserialize data for {key}: {error}"
            raise DeserializeError(msg) from e

    async def scan(self, pattern: str) -> AsyncIterator[str]:
        """Scan Redis for a given key pattern, returning each key.

        Parameters
        ----------
        pattern
            Key pattern to scan for.

        Yields
        ------
        str
            Each key matching that pattern.
        """
        async for key in self._redis.scan_iter(match=pattern):
            yield key.decode()

    async def store(
        self, key: str, obj: S, lifetime: Optional[int] = None
    ) -> None:
        """Store an object.

        Parameters
        ----------
        key
            The key for the object.
        obj
            The object to store.
        lifetime
            The object lifetime in seconds.  The object should expire from the
            data store after that many seconds after the current time.  Pass
            `None` if the object should not expire.
        """
        data = self._serialize(obj)
        await self._redis.set(key, data, ex=lifetime)

    def _serialize(self, obj: S) -> bytes:
        """Serialize a Pydantic object to bytes that can be stored by Redis.

        Parameters
        ----------
        obj
            The Pydantic object to serialize.

        Returns
        -------
        bytes
            The serialized object.
        """
        return obj.json().encode()

    def _deserialize(self, data: bytes) -> S:
        """Deserialize bytes into a Pydantic object.

        Parameters
        ----------
        data
            The data to deserialize.

        Returns
        -------
        S
            The deserialized Pydantic object.
        """
        return self._datatype.parse_raw(data.decode())


class EncryptedPydanticRedisStorage(PydanticRedisStorage[S]):
    """A Pydantic-based Redis store that encrypts data.

    Parameters
    ----------
    datatype
        The class of object being stored (a Pydantic model).
    redis
        A Redis client configured to talk to the backend store.
    encryption_key
        Encryption key. Must be a `~cryptography.fernet.Fernet` key. Generate
        a key with ``Fernet.generate_key().decode()``.
    """

    def __init__(
        self,
        *,
        datatype: type[S],
        redis: redis.Redis,
        encryption_key: str,
    ) -> None:
        super().__init__(datatype=datatype, redis=redis)
        self._fernet = Fernet(encryption_key.encode())

    def _serialize(self, obj: S) -> bytes:
        data = obj.json().encode()
        return self._fernet.encrypt(data)

    def _deserialize(self, data: bytes) -> S:
        data = self._fernet.decrypt(data)
        return self._datatype.parse_raw(data.decode())
