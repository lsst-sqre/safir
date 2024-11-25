"""Store Pydantic models in Redis with optional encryption."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Generic, TypeVar

try:
    import redis.asyncio as redis
except ImportError as e:
    raise ImportError(
        "The safir.redis module requires the redis extra. "
        "Install it with `pip install safir[redis]`."
    ) from e
from cryptography.fernet import Fernet
from pydantic import BaseModel

from safir.slack.blockkit import (
    SlackCodeBlock,
    SlackException,
    SlackMessage,
    SlackTextField,
)

__all__ = [
    "DeserializeError",
    "EncryptedPydanticRedisStorage",
    "PydanticRedisStorage",
]


class DeserializeError(SlackException):
    """Raised when a stored Pydantic object in Redis cannot be decoded (and
    possibly decrypted) or deserialized.

    Parameters
    ----------
    msg
        A description of the error.
    key
        The key of the object that could not be deserialized.
    error
        The exception's message from the deserialization attempt.
    """

    def __init__(self, msg: str, key: str, error: str) -> None:
        super().__init__(msg)
        self.key = key
        self.error = error

    def to_slack(self) -> SlackMessage:
        message = super().to_slack()
        message.fields.append(SlackTextField(heading="Key", text=self.key))
        message.blocks.append(SlackCodeBlock(heading="Error", code=self.error))
        return message


#: Type variable of Pydantic object being stored in `PydanticRedisStorage`.
S = TypeVar("S", bound="BaseModel")


class PydanticRedisStorage(Generic[S]):
    """JSON-serialized encrypted storage in Redis.

    Parameters
    ----------
    datatype
        The class of object being stored (a Pydantic model).
    redis
        A Redis client configured to talk to the backend store.
    key_prefix
        A prefix to prepend to all Redis keys. Setting a prefix ensures that
        all objects stored through this class share the same redis key
        prefix. This is useful if multiple storage classes share the same
        Redis database. The keys that you use to store objects (e.g. the
        `store` method) and the key you get back from the `scan` method do
        not include this prefix.
    """

    def __init__(
        self, *, datatype: type[S], redis: redis.Redis, key_prefix: str = ""
    ) -> None:
        self._datatype = datatype
        self._redis = redis
        self._key_prefix = key_prefix

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
        count = await self._redis.delete(self._prefix_key(key))
        return count > 0

    async def delete_all(self, pattern: str) -> None:
        """Delete all stored objects.

        Parameters
        ----------
        pattern
            Glob pattern matching the keys to purge, such as ``oidc:*``.
        """
        async for key in self._redis.scan_iter(self._prefix_key(pattern)):
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
        full_key = self._prefix_key(key)
        data = await self._redis.get(full_key)
        if not data:
            return None

        try:
            return self._deserialize(data)
        except Exception as e:
            error = f"{type(e).__name__}: {e!s}"
            msg = f"Cannot deserialize data for key {full_key}"
            raise DeserializeError(msg, key=full_key, error=error) from e

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
        async for key in self._redis.scan_iter(
            match=self._prefix_key(pattern)
        ):
            yield key.decode().removeprefix(self._key_prefix)

    async def store(
        self, key: str, obj: S, lifetime: int | None = None
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
        await self._redis.set(self._prefix_key(key), data, ex=lifetime)

    def _prefix_key(self, key: str) -> str:
        """Compute the full Redis key, given the key prefix."""
        return f"{self._key_prefix}{key}"

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
        return obj.model_dump_json().encode()

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
        return self._datatype.model_validate_json(data.decode())


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
    key_prefix
        A prefix to prepend to all Redis keys. Setting a prefix ensures that
        all objects stored through this class share the same redis key
        prefix. This is useful if multiple storage classes share the same
        Redis database. The keys that you use to store objects (e.g. the
        `store` method) and the key you get back from the `scan` method do
        not include this prefix.
    """

    def __init__(
        self,
        *,
        datatype: type[S],
        redis: redis.Redis,
        encryption_key: str,
        key_prefix: str = "",
    ) -> None:
        super().__init__(datatype=datatype, redis=redis, key_prefix=key_prefix)
        self._fernet = Fernet(encryption_key.encode())

    def _serialize(self, obj: S) -> bytes:
        data = obj.model_dump_json().encode()
        return self._fernet.encrypt(data)

    def _deserialize(self, data: bytes) -> S:
        data = self._fernet.decrypt(data)
        return self._datatype.model_validate_json(data.decode())
