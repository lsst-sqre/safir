.. _kafka-integration:

======================
Integrating with Kafka
======================

If you want to build an async message-based app, or need to otherwise publish or consume messages to and from Kafka, Safir provides a `~safir.kafka` subpackage with some tools to make some parts of the integration easier.

Kafka support in Safir is optional.
To use it, depend on ``safir[kafka]``.

Guides
======

.. toctree::
   :titlesonly:

   kafka-connection-settings
   pydantic-schema-manager
   faststream
   testing
