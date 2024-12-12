#!/usr/bin/env bash
set -ex
id

OUT_DIR=$1
SERVER_HOSTNAME=$2

PASSWORD=password

CA_CERT=ca.crt
CA_KEY=ca.key

SERVER_TRUSTSTORE=server.truststore.jks
SERVER_KEYSTORE=server.keystore.jks
SERVER_CSR=server.csr
SERVER_CERT_SIGNED=server.crt

CLIENT_TRUSTSTORE=client.truststore.jks
CLIENT_KEYSTORE=client.keystore.jks
CLIENT_CSR=client.csr
CLIENT_CERT_SIGNED=client.crt
CLIENT_KEYSTORE_P12=client.keystore.p12
CLIENT_KEY=client.key

mkdir -p "${OUT_DIR}"
cd "${OUT_DIR}" || exit

# PEM CA cert and key
openssl req -new -x509 -addext 'keyUsage=critical, cRLSign, digitalSignature, keyCertSign' -keyout ${CA_KEY} -out ${CA_CERT} -days 365 -subj "/CN=ca" -nodes

# Server truststore CA cert
keytool -keystore ${SERVER_TRUSTSTORE} -alias CARoot -storepass ${PASSWORD} -importcert -file ${CA_CERT} -noprompt

# Server keystore CA cert
keytool -keystore ${SERVER_KEYSTORE} -alias CARoot -storepass ${PASSWORD} -importcert -file ${CA_CERT} -noprompt

# Server keystore private key
keytool -keystore ${SERVER_KEYSTORE} -alias server -validity 365 -genkey -keyalg RSA -storepass ${PASSWORD} -keypass ${PASSWORD} -dname "CN=${SERVER_HOSTNAME}" -ext SAN=DNS:kafka
#
# CSR for server cert signed by CA
# Generate PEM CA-signed server cert
# Import the signed server cert back into the server keystore
keytool -keystore ${SERVER_KEYSTORE} -alias server -storepass ${PASSWORD} -certreq -file ${SERVER_CSR}
openssl x509 -req -CA ${CA_CERT} -CAkey ${CA_KEY} -in ${SERVER_CSR} -out ${SERVER_CERT_SIGNED} -days 365 -CAcreateserial
keytool -keystore ${SERVER_KEYSTORE} -alias server -storepass ${PASSWORD} -importcert -file ${SERVER_CERT_SIGNED} -noprompt
# Client truststore CA cert
keytool -keystore ${CLIENT_TRUSTSTORE} -alias CARoot -storepass ${PASSWORD} -importcert -file ${CA_CERT} -noprompt

# Client keystore CA cert
keytool -keystore ${CLIENT_KEYSTORE} -alias CARoot -storepass ${PASSWORD} -importcert -file ${CA_CERT} -noprompt

# Client keystore private key
keytool -keystore ${CLIENT_KEYSTORE} -alias client -validity 365 -genkey -keyalg RSA -storepass ${PASSWORD} -keypass ${PASSWORD} -dname "CN=client" -ext SAN=DNS:client

# CSR for CA-signed client cert
# Generate PEM CA-signed client cert
# Import the signed client cert back into the client keystore
keytool -keystore ${CLIENT_KEYSTORE} -alias client -storepass ${PASSWORD} -certreq -file ${CLIENT_CSR}
openssl x509 -req -CA ${CA_CERT} -CAkey ${CA_KEY} -in ${CLIENT_CSR} -out ${CLIENT_CERT_SIGNED} -days 365 -CAcreateserial
keytool -keystore ${CLIENT_KEYSTORE} -alias client -storepass ${PASSWORD} -importcert -file ${CLIENT_CERT_SIGNED} -noprompt

# Get a PEM version of the client key
keytool -importkeystore -srckeystore ${CLIENT_KEYSTORE} -srcstorepass ${PASSWORD} -destkeystore ${CLIENT_KEYSTORE_P12} -deststoretype PKCS12 -srcalias client -deststorepass ${PASSWORD} -destkeypass ${PASSWORD}
openssl pkcs12 -in ${CLIENT_KEYSTORE_P12} -nodes -nocerts -out ${CLIENT_KEY} -passin pass:${PASSWORD}

# Credentials (password) file
echo ${PASSWORD} >credentials

# For SASL: We don't care about server/broker auth but we have to put _something_ here.
echo 'KafkaServer { org.apache.kafka.common.security.scram.ScramLoginModule required username="_" password="_"; };' >"$1/kafka_server_jaas.conf"

# Clean up
rm ${SERVER_CSR} ${CLIENT_CSR} ${CLIENT_KEYSTORE_P12}
