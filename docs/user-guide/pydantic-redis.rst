#################################
Storing Pydantic objects in Redis
#################################

Safir provides a `~safir.redis.PydanticRedisStorage` class that can conveniently store Pydantic objects in Redis.
The advantage of using Pydantic models with Redis is that data usage is validated during developed and validated at runtime.
Safir also provides a subclass, `~safir.redis.EncryptedPydanticRedisStorage`, that encrypts data before storing it in Redis.

.. important::

   To use `safir.redis`, you must install Safir with its ``redis`` extra: that is, ``safir[redis]``.

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
   from safir.redis import PydanticRedisStorage


   class MyModel(BaseModel):
       id: int
       name: str


   redis_client = redis.Redis("redis://localhost:6379/0")
   mymodel_storage = PydanticRedisStorage(MyModel, redis_client)

Use the `~safir.redis.PydanticRedisStorage.store` method to store a Pydantic object in Redis with a specific key:

.. code-block:: python

   await mymodel_storage.store("people:1", MyModel(id=1, name="Drew"))
   await mymodel_storage.store("people:2", MyModel(id=2, name="Blake"))

You can get objects back by their key:

.. code-block:: python

   drew = await mymodel_storage.get("people:1")
   assert drew.id == 1
   assert drew.name == "Drew"

You can scan for all keys that match a pattern with the `~safir.redis.PydanticRedisStorage.scan` method:

.. code-block:: python

   async for key in mymodel_storage.scan("people:*"):
       m = await mymodel_storage.get(key)
       print(m)

You can also delete objects by key using the `~safir.redis.PydanticRedisStorage.delete` method:

.. code-block:: python

   await mymodel_storage.delete("people:1")

It's also possible to delete all objects at once with keys that match a pattern using the `~safir.redis.PydanticRedisStorage.delete_all` method:

.. code-block:: python

   await mymodel_storage.delete_all("people:*")

Encrypting data with EncryptedPydanticRedisStorage
==================================================

`~safir.redis.EncryptedPydanticRedisStorage` is a subclass of `~safir.redis.PydanticRedisStorage` that encrypts data before storing it in Redis.
It also decrypts data after retrieving it from Redis (assuming the key is correct).

To use `~safir.redis.EncryptedPydanticRedisStorage` you must provide a Fernet key.
A convenient way to generate a Fernet key is with the `cryptography.fernet.Fernet.generate_key` function from the `cryptography`_ Python package:

.. code-block:: python

   from cryptography.fernet import Fernet

   print(Fernet.generate_key().decode())

Conventionally, you'll store this key in a persistent secret store, such as 1Password or Vault (see the `Phalanx documentation <https://phalanx.lsst.io/developers/add-a-onepassword-secret.html>`__) and then make this key available to your application through an environment variable to your configuration class.
Then pass the key's value to `~safir.redis.EncryptedPydanticRedisStorage` with the ``encryption_key`` parameter:

.. code-block:: python

   from safir.redis import EncryptedPydanticRedisStorage

   redis_client = redis.Redis(config.redis_url)
   mymodel_storage = EncryptedPydanticRedisStorage(
       datatype=MyModel,
       redis=redis_client,
       encryption_key=config.encryption_key,
   )

Once set up, you can interact with this storage class exactly like `~safir.redis.PydanticRedisStorage`, except that all data is encrypted in Redis.

Multi-tentant storage with key prefixes
=======================================

`~safir.redis.PydanticRedisStorage` and `~safir.redis.EncryptedPydanticRedisStorage` both allow you to specify a prefix string that is automatically applied to the keys of an objects stored through that class.
Once set, your application does not need to worry about consistently using this prefix.

A common use case for a key prefix is if multiple stores share the same Redis database.
Each `~safir.redis.PydanticRedisStorage` instance works with a specific Pydantic model type, so if your application needs to store multiple types of objects in Redis, you can use multiple instances of `~safir.redis.PydanticRedisStorage` with different key prefixes.

.. code-block:: python

   class PetModel(BaseModel):
       id: int
       name: str
       age: int


   class CustomerModel(BaseModel):
       id: int
       name: str
       email: str


   redis_client = redis.Redis(config.redis_url)

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
