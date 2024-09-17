#!/bin/bash
# Gernerate valid (but useless) certs that last for 1000 years
# to test kafka client construction.

# Clean up
rm -f ./*.crt ./*.key ./*.req ./*.pem

# Server CA cert
openssl req -new -x509 -keyout dummy-server-ca.key -out dummy-server-ca.crt -days 365000 -subj '/CN=ca' -nodes
rm dummy-server-ca.key

# User cert and key
openssl req -new -x509 -keyout dummy-user.key -out dummy-user.crt -days 365000 -subj '/CN=user' -nodes
