#!/usr/bin/env bash
# kafka-setup job (INFRASTRUCTURE Â§5.2, TR-SEC-7): SCRAM users, topics, ACLs. Idempotent; runs on every deploy.
# Runs inside the apache/kafka image on the INTERNAL (mTLS) listener with the broker certificate, which is a
# super user; that is how the very first SCRAM user (admin) gets created in KRaft.
#   env: BOOTSTRAP (kafka1:9094,...), REPLICATION (3), SECRETS_DIR (/run/secrets)
set -euo pipefail
B=${BOOTSTRAP:-kafka1:9094,kafka2:9094,kafka3:9094}
S=${SECRETS_DIR:-/run/secrets}
BIN=/opt/kafka/bin
CFG=/tmp/admin.properties
cat > "$CFG" <<EOF
security.protocol=SSL
ssl.keystore.type=PEM
ssl.keystore.location=$S/kafka.pem
ssl.truststore.type=PEM
ssl.truststore.location=$S/ca.pem
EOF

until $BIN/kafka-topics.sh --bootstrap-server "$B" --command-config "$CFG" --list >/dev/null 2>&1; do
  echo "waiting for kafka"; sleep 3
done

# 1. SCRAM credentials: admin (ops, over SASL_SSL) and every service principal.
USERS="admin identity catalog inventory order document notification media relay exporter"
for u in $USERS; do
  $BIN/kafka-configs.sh --bootstrap-server "$B" --command-config "$CFG" --alter --entity-type users \
    --entity-name "$u" --add-config "SCRAM-SHA-512=[password=$(cat "$S/kafka_$u")]" >/dev/null
done
echo "scram users ready"

# 2. Topics (shared script; same list as dev).
BOOTSTRAP="$B" REPLICATION="${REPLICATION:-3}" COMMAND_CONFIG="$CFG" bash /setup/create-topics.sh

# 3. ACLs: producers write only their own topics; consumers read their topics via their own group and may
#    write (and re-read) only the retry/DLQ topics of what they consume (TAD §5.3). One kafka-acls call per
#    rule set (each call starts a JVM), with many --topic arguments.
acl() { $BIN/kafka-acls.sh --bootstrap-server "$B" --command-config "$CFG" --add --force "$@" >/dev/null; }
topics() { local a=(); for t in "$@"; do a+=(--topic "$t"); done; echo "${a[@]}"; }
produce() { # principal topic...
  local p=$1; shift
  # shellcheck disable=SC2046
  acl --allow-principal "User:$p" --operation Write --operation Describe $(topics "$@")
  acl --allow-principal "User:$p" --operation IdempotentWrite --cluster
}
consume() { # principal group topic...
  local p=$1 g=$2; shift 2
  local retry=() rw=()
  for t in "$@"; do retry+=("$t.retry"); rw+=("$t.retry" "$t.dlq"); done
  # shellcheck disable=SC2046
  acl --allow-principal "User:$p" --operation Read --operation Describe $(topics "$@" "${retry[@]}")
  # shellcheck disable=SC2046
  acl --allow-principal "User:$p" --operation Write --operation Describe $(topics "${rw[@]}")
  acl --allow-principal "User:$p" --operation Read --group "$g" --resource-pattern-type prefixed
}

# Relays publish every service's outbox (one principal for all relays).
produce relay identity.user.events catalog.product.events inventory.stock.events order.events document.events media.jobs audit.events
produce media media.results

consume identity identity identity.user.events audit.events
consume catalog catalog identity.user.events media.results inventory.stock.events
consume inventory inventory order.events catalog.product.events
consume order order inventory.stock.events catalog.product.events document.events identity.user.events
consume document document order.events
consume notification notification identity.user.events order.events document.events inventory.stock.events
consume media media media.jobs
acl --allow-principal User:exporter --operation Describe --topic '*' --group '*'
acl --allow-principal User:exporter --operation Describe --cluster
echo "acls ready"
rm -f "$CFG"
