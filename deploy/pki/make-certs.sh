#!/usr/bin/env bash
# Private CA + server/client certificates for MongoDB, Kafka and Redis (INFRASTRUCTURE §5, TR-SEC-7).
# Idempotent: an existing CA or certificate is kept. Output goes to deploy/secrets/pki/ (not in git).
#
#   deploy/pki/make-certs.sh [out-dir]
#
# Host names come from PKI_HOSTS (space separated, "name[:extra-san,...]"); defaults match INFRASTRUCTURE §3.1.
# Each cert <name>.pem = cert + key (the format mongod/redis/kafka(PEM) read); ca.pem is the trust anchor.
set -euo pipefail

OUT=${1:-$(cd "$(dirname "$0")/.." && pwd)/secrets/pki}
DAYS_CA=${DAYS_CA:-3650}
DAYS_LEAF=${DAYS_LEAF:-825}
PKI_HOSTS=${PKI_HOSTS:-"sia-host.cimh.local:mongo1,redis,kafka1,kafka2,kafka3,localhost sia-pi-a.cimh.local:mongo2 sia-pi-b.cimh.local:mongo3"}
PKI_CLIENTS=${PKI_CLIENTS:-"svc-backup"}

mkdir -p "$OUT"; chmod 700 "$OUT"; cd "$OUT"
umask 077

if [[ ! -f ca.key ]]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out ca.key 2>/dev/null
  # Explicit extensions only (no openssl.cnf defaults, which would duplicate basicConstraints). Python 3.13's
  # strict verification requires keyUsage on the CA and AKI on leaves.
  openssl req -new -key ca.key -subj "/O=CIMH/CN=CIMH Stores Private CA" -out ca.csr
  printf 'basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n' > ca.ext
  openssl x509 -req -in ca.csr -signkey ca.key -sha256 -days "$DAYS_CA" -extfile ca.ext -out ca.pem 2>/dev/null
  rm -f ca.csr ca.ext
  echo "created CA"
fi

issue() { # name sans usage
  local name=$1 sans=$2 usage=$3
  [[ -f "$name.pem" ]] && return 0
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$name.key" 2>/dev/null  # PKCS#8: Kafka needs it. AKI/SKI below: Python 3.13 strict verification needs them
  openssl req -new -key "$name.key" -subj "/O=CIMH/OU=stores/CN=$name" -out "$name.csr"
  printf 'basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\nextendedKeyUsage=%s\n%s' \
    "$usage" "${sans:+subjectAltName=$sans}" > "$name.ext"
  openssl x509 -req -in "$name.csr" -CA ca.pem -CAkey ca.key -CAcreateserial -days "$DAYS_LEAF" -sha256 \
    -extfile "$name.ext" -out "$name.crt" 2>/dev/null
  cat "$name.crt" "$name.key" > "$name.pem"
  rm -f "$name.csr" "$name.ext"
  echo "issued $name"
}

for spec in $PKI_HOSTS; do
  host=${spec%%:*}; extra=${spec#*:}; [[ "$extra" == "$spec" ]] && extra=""
  sans="DNS:$host"
  IFS=',' read -ra names <<< "$extra"
  for n in "${names[@]}"; do [[ -n "$n" ]] && sans="$sans,DNS:$n"; done
  # Server certs also act as clients (replica-set members and Kafka brokers talk to each other).
  issue "$host" "$sans" "serverAuth,clientAuth"
done
for c in $PKI_CLIENTS; do issue "$c" "" "clientAuth"; done

chmod 600 ./*
echo "PKI ready in $OUT (keep ca.key offline after provisioning)"
