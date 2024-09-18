#!/usr/bin/env bash
set -e

PASSWORD=password

cert_dir=$1
mkdir -p "$cert_dir"
cd "$cert_dir" || exit
rm -rf ./*.crt ./*.key ./*.jks ./*.csr ./*.p12

# Create CA cert and key
openssl req \
  -new -x509 \
  -keyout ca.key \
  -out ca.crt \
  -days 365000 \
  -subj "/CN=ca" \
  -nodes

# Server truststore
keytool \
  -keystore server.truststore.jks \
  -alias CARoot \
  -storepass ${PASSWORD} \
  -importcert \
  -file ca.crt \
  -noprompt

# Client truststore
keytool \
  -keystore client.truststore.jks \
  -alias CARoot \
  -storepass ${PASSWORD} \
  -importcert \
  -file ca.crt \
  -noprompt

# Server keystore
keytool \
  -keystore server.keystore.jks \
  -alias server \
  -validity 365 \
  -genkey \
  -keyalg RSA \
  -storepass ${PASSWORD} \
  -keypass ${PASSWORD} \
  -dname "CN=localhost" \
  -ext SAN=DNS:kafka

# Client keystore
keytool \
  -keystore client.keystore.jks \
  -alias client \
  -validity 365 \
  -genkey \
  -keyalg RSA \
  -storepass ${PASSWORD} \
  -keypass ${PASSWORD} \
  -dname "CN=client" \
  -ext SAN=DNS:client

# Server CSR
keytool \
  -keystore server.keystore.jks \
  -alias server \
  -storepass ${PASSWORD} \
  -certreq \
  -file server.csr

# Client CSR
keytool \
  -keystore client.keystore.jks \
  -alias client \
  -storepass ${PASSWORD} \
  -certreq \
  -file client.csr

# Server cert
openssl \
  x509 -req \
  -CA ca.crt \
  -CAkey ca.key \
  -in server.csr \
  -out server.crt \
  -days 365000 \
  -CAcreateserial

# Client cert
openssl \
  x509 -req \
  -CA ca.crt \
  -CAkey ca.key \
  -in client.csr \
  -out client.crt \
  -days 365000 \
  -CAcreateserial

# Add CA cert to server keystore
keytool \
  -keystore server.keystore.jks \
  -alias CARoot \
  -storepass ${PASSWORD} \
  -importcert \
  -file ca.crt \
  -noprompt

# Add CA cert to client keystore
keytool \
  -keystore client.keystore.jks \
  -alias CARoot \
  -storepass ${PASSWORD} \
  -importcert \
  -file ca.crt \
  -noprompt

# Add client cert to client keystore
keytool \
  -keystore client.keystore.jks \
  -alias client \
  -storepass ${PASSWORD} \
  -importcert \
  -file client.crt \
  -noprompt

# Add server cert to server keystore
keytool \
  -keystore server.keystore.jks \
  -alias server \
  -storepass ${PASSWORD} \
  -importcert \
  -file server.crt \
  -noprompt

# Export client key to P12
keytool -importkeystore \
  -srckeystore client.keystore.jks \
  -srcstorepass ${PASSWORD} \
  -destkeystore client.keystore.p12 \
  -deststoretype PKCS12 \
  -srcalias client \
  -deststorepass ${PASSWORD} \
  -destkeypass ${PASSWORD}

# Convert to PEM
openssl pkcs12 -in client.keystore.p12 -nodes -nocerts -out client.key -passin pass:${PASSWORD}

# Credentials (password) file
echo ${PASSWORD} >credentials

echo 'KafkaServer { org.apache.kafka.common.security.scram.ScramLoginModule required username="_" password="_"; };' >"$1/kafka_server_jaas.conf"
