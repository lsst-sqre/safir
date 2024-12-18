### Bug fixes

- Unset the `ssl.VERIFY_X509_STRICT` flag in SSL contexts used for Kafka connections. Python 3.13 enables this flag by default, and the current certs that Strimzi generates for these Kafka endpoints are missing an Authority Key Identifier, which prevents connections when the flag is set.
