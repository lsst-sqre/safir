#########################
Kafka connection settings
#########################

Safir provides a `Pydantic BaseSettings`_ model to get correct and valid Kafka connection settings into an application.
The `~safir.kafka.KafkaConnectionSettings` model supports different authentication methods, which each have different sets of required settings.
All of these settings can be provided in ``KAFKA_`` prefixed environment variables.
Instances of this model have properties that can be used to construct different types of Kafka_ clients:

.. code-block:: python

   from aiokafka import AIOKafkaConsumer
   from aiokafka.admin.client import AIOKafkaAdminClient
   from faststream.kafka import KafkaBroker

   from safir.kafka import KafkaConnectionSettings


   config = KafkaConnectionSettings()

   broker = KafkaBroker(**config.to_faststream_params())
   consumer = AIOKafkaConsumer(**config.to_aiokafka_params)
   admin = AIOKafkaAdminClient(**config.to_aiokafka_params)

This model supports four security protocols.
If your application is running in Phalanx, you likely should be using the Sasquatch_-managed Kafka cluster, and generating the necessary values `like this <https://sasquatch.lsst.io/user-guide/directconnection.html>`__.

SSL
---

This is the preferred protocol. Authentication is done via mutual TLS, and all traffic goes over a TLS-encrypted channel.
If your application is running in Phalanx, you likely should be using the Sasquatch-managed Kafka cluster, and generating these TLS credentials `like this <https://sasquatch.lsst.io/user-guide/directconnection.html>`__.

.. code-block:: shell

   KAFKA_SECURITY_PROTOCOL=SSL
   KAFKA_BOOSTRAP_SERVERS=kafka-1:9092,kafka2-9092
   KAFKA_CLUSTER_CA_PATH=/some/path/ca.crt
   KAFKA_CLIENT_CERT_PATH=/some/path/user.crt
   KAFKA_CLIENT_KEY_PATH=/some/path/user.key

SASL_SSL
--------

This method is sometimes useful for clients running outside the Phalanx environment where Kafka is running.
It uses a username/password combo to authenticate, and all traffic is sent over a TLS-encrypted connection.

.. code-block:: shell

   KAFKA_SECURITY_PROTOCOL=SASL_SSL
   KAFKA_BOOSTRAP_SERVERS=kafka-1:9092,kafka2-9092
   KAFKA_SASL_USERNAME=myusername
   KAFKA_SASL_PASSWORD=mypassword

   # Optional, needed only if the client doesn't already trust the cluster cert
   KAFKA_CLUSTER_CA_PATH=/some/path/ca.crt

SASL_PLAINTEXT
--------------

This protocol should only be used in development envioronments.
It uses a username/password combo to authenticate, but all communication goes over unencrypted channels.

.. code-block:: shell

   KAFKA_SECURITY_PROTOCOL=SASL_PLAINTEXT
   KAFKA_BOOSTRAP_SERVERS=kafka-1:9092,kafka2-9092
   KAFKA_SASL_USERNAME=myusername
   KAFKA_SASL_PASSWORD=mypassword

   # Optional, needed only if the client doesn't already trust the cluster cert
   KAFKA_CLUSTER_CA_PATH=/some/path/ca.crt

PLAINTEXT
---------

This protocol should only be used in development envioronments.
There is no authentication required, and all communication goes over unencrypted channels.

.. code-block:: shell

   KAFKA_SECURITY_PROTOCOL=PLAINTEXT
   KAFKA_BOOSTRAP_SERVERS=kafka-1:9092,kafka2-9092
