#################################
Storing Pydantic objects in Redis
#################################

Safir provides a `~safir.pydanticredis.PydanticRedisStorage` class that can conveniently store Pydantic objects in Redis.
The advantage of using Pydantic models with Redis is that data usage is validated during developed and validated at runtime.
Safir also provides a subclass, `~safir.pydanticredis.EncryptedPydanticRedisStorage`, that encrypts data before storing it in Redis.

Basic usage
===========

`~safir.redis.PydanticRedisStorage` works with an asyncio Redis client (`redis.asyncio.client.Redis`) from `redis-py`_.
You supply the storage class type as a parameter.
All objects stored in the storage must be instances of this type, and objects in Redis will be parsed and validated as this type.
If you need to store multiple types of Pydantic objects in Redis, you can create separate instances of `~safir.redis.PydanticRedisStorage` for each type.

Here is a basic set up:

.. code-block:: python

   import redis.asyncio as redis
   from pydantic import BaseModel, Field
   from safir.pydanticredis import PydanticRedisStorage


   class MyModel(BaseModel):
       id: int
       name: str


   redis_client = redis.Redis("redis://localhost:6379/0")
   mymodel_storage = PydanticRedisStorage(MyModel, redis_client)

Use the `~safir.pydanticredis.PydanticRedisStorage.store` method to store a Pydantic object in Redis with a specific key:

.. code-block:: python

   await mymodel_storage.store("people:1", MyModel(id=1, name="Drew"))
   await mymodel_storage.store("people:2", MyModel(id=2, name="Blake"))

You can get objects back by their key:

.. code-block:: python

   drew = await mymodel_storage.get("people:1")
   assert drew.id == 1
   assert drew.name == "Drew"

You can scan for all keys that match a pattern with the `~safir.pydanticredis.PydanticRedisStorage.scan` method:

.. code-block:: python

   async for key in mymodel_storage.scan("people:*"):
       m = await mymodel_storage.get(key)
       print(m)

You can also delete objects by key using the `~safir.pydanticredis.PydanticRedisStorage.delete` method:

.. code-block:: python

   await mymodel_storage.delete("people:1")

It's also possible to delete all objects at once with keys that match a pattern using the `~safir.pydanticredis.PydanticRedisStorage.delete_all` method:

.. code-block:: python

   await mymodel_storage.delete_all("people:*")

Encrypting data with EncryptedPydanticRedisStorage
==================================================

`~safir.pydanticredis.EncryptedPydanticRedisStorage` is a subclass of `~safir.pydanticredis.PydanticRedisStorage` that encrypts data before storing it in Redis.
It also decrypts data after retrieving it from Redis (assuming the key is correct).

To use `~safir.pydanticredis.EncryptedPydanticRedisStorage` you must provide a Fernet key.
A convenient way to generate a Fernet key is with the `cryptography.fernet.Fernet.generate_key` function from the `cryptography`_ Python package:

.. code-block:: python

   from cryptography.fernet import Fernet

   print(Fernet.generate_key().decode())

Conventionally, you'll store this key in a persistent secret store, such as 1Password or Vault (see the `Phalanx documentation <https://phalanx.lsst.io/developers/add-a-onepassword-secret.html>`__) and then make this key available to your application through an environment variable to your configuration class.
Then pass the key's value to `~safir.pydanticredis.EncryptedPydanticRedisStorage` with the ``encryption_key`` parameter:

.. code-block:: python

   from safir.pydanticredis import EncryptedPydanticRedisStorage

   redis_client = redis.Redis(config.redis_url)
   mymodel_storage = EncryptedPydanticRedisStorage(
       datatype=MyModel,
       redis=redis_client,
       encryption_key=config.encryption_key,
   )

Once set up, you can interact with this storage class exactly like `~safir.pydanticredis.PydanticRedisStorage`, except that all data is encrypted in Redis.
