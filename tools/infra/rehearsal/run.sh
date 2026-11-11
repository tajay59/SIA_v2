#!/usr/bin/env bash
# Rehearse the production platform on one Docker host and check the P1 exit criteria that can be checked
# without CIMH hardware (IMPLEMENTATION_PLAN P1, INFRASTRUCTURE §10 steps 4-9):
#   - private CA, secrets, Redis ACL rendered by the real scripts
#   - 3-member replica set with TLS + keyfile + per-service users: 1 primary + 2 secondaries; failover and
#     priority-10 fail-back
#   - Kafka x3 KRaft over mTLS/SASL_SSL with SCRAM users, topics and ACLs (allowed and denied cases)
#   - Redis ACLs (allowed and denied cases)
#   - identity-svc + its outbox relay on that platform: register -> event on identity.user.events
#   - backup (mongodump --oplog from a secondary -> restic) and restore into a fresh instance, counts verified
#   - resilience (TEST_STRATEGY §7): one Kafka broker down, outbox relay down + backlog metric, Redis restart (AOF)
#
#   tools/infra/rehearsal/run.sh            # run everything, tear down at the end
#   KEEP=1 tools/infra/rehearsal/run.sh     # leave the stack running for a look around
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: don't rewrite /run/secrets/... arguments

HERE=$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))   # pwd -W: Windows path for docker under Git Bash
ROOT=$(cd "$HERE/../../.." && (pwd -W 2>/dev/null || pwd))
WORK=${REHEARSAL_DIR:-${TMPDIR:-/tmp}/sia-rehearsal}
SEC="$WORK/secrets"
# A fresh volume name per run: Docker Desktop can serve stale subpath mounts of a re-created volume.
SECRETS_VOLUME=sia-rehearsal-secrets-$(date +%s)
export SECRETS_VOLUME
C="docker compose -f $HERE/compose.yml"
export KAFKA_CLUSTER_ID=${KAFKA_CLUSTER_ID:-$(docker run --rm --entrypoint /opt/kafka/bin/kafka-storage.sh apache/kafka:3.9.0 random-uuid | tr -d '\r')}
export VLAN_IP=127.0.0.1 HELLO_SVC_DIGEST=sha256:unused IDENTITY_SVC_DIGEST=sha256:unused CATALOG_SVC_DIGEST=sha256:unused MEDIA_WORKER_DIGEST=sha256:unused INVENTORY_SVC_DIGEST=sha256:unused ORDER_SVC_DIGEST=sha256:unused DOCUMENT_SVC_DIGEST=sha256:unused NOTIFICATION_SVC_DIGEST=sha256:unused
PASS=0; FAIL=0
ok() { echo "  PASS  $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
check() { local name=$1; shift; if "$@" >/dev/null 2>&1; then ok "$name"; else bad "$name"; fi; }
mongo_root() { $C exec -T mongo1 mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host sia-host.cimh.local \
  -u root -p "$(cat "$SEC/mongo_root")" --authenticationDatabase admin "$@"; }

start() { # services...: start and wait; on failure show why (CI has no other view)
  local out
  if ! out=$($C up -d --quiet-pull --wait --wait-timeout 180 "$@" 2>&1); then
    bad "start $*"; echo "$out" | tail -15; docker version --format 'engine {{.Server.Version}}'
    $C ps -a; $C logs --tail 40 "$@"; exit 1
  fi
}

cleanup() {
  if [[ "${KEEP:-}" != 1 ]]; then
    $C --profile tools down -v --remove-orphans >/dev/null 2>&1 || true
    docker volume rm $SECRETS_VOLUME >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# Start from nothing: remove any earlier rehearsal containers and volumes.
docker ps -aq --filter label=com.docker.compose.project=sia-rehearsal | xargs -r docker rm -f >/dev/null
docker volume ls -q --filter label=com.docker.compose.project=sia-rehearsal | xargs -r docker volume rm >/dev/null
docker volume ls -q | grep '^sia-rehearsal-secrets' | xargs -r docker volume rm >/dev/null || true

echo "== 1. PKI, secrets, Redis ACL (deploy/pki, deploy/scripts/make-secrets.sh, deploy/redis/render-acl.sh)"
rm -rf "$WORK"; mkdir -p "$SEC"
bash "$ROOT/deploy/pki/make-certs.sh" "$SEC/pki" >/dev/null
REDIS_HOST=redis:6379 bash "$ROOT/deploy/scripts/make-secrets.sh" "$SEC" >/dev/null
bash "$ROOT/deploy/redis/render-acl.sh" "$SEC" >/dev/null
echo dummy > "$SEC/smtp_password"
# The restore target in the rehearsal has no auth; production restores into staging with its own root user.
printf 'mongodb://mongo-restore:27017/?directConnection=true' > "$SEC/mongo_url_restore"
check "CA and leaf certificates issued" test -s "$SEC/pki/sia-host.cimh.local.pem"
check "secrets generated" test -s "$SEC/jwt_private_key"

echo "== 2. secrets volume (per-container owner, 0400)"
docker volume rm $SECRETS_VOLUME >/dev/null 2>&1 || true
docker volume create $SECRETS_VOLUME >/dev/null
tar -C "$SEC" -cf - . | docker run --rm -i -v $SECRETS_VOLUME:/s alpine:3.20 sh -c '
  set -e; mkdir /in; tar -C /in -xf -
  put() { d=$1; uid=$2; shift 2; mkdir -p /s/$d; for f in "$@"; do cp "/in/$f" "/s/$d/$(basename "$f")"; done; chown -R "$uid" /s/$d; chmod 500 /s/$d; chmod 400 /s/$d/*; }
  for m in 1 2 3; do
    case $m in 1) h=sia-host.cimh.local;; 2) h=sia-pi-a.cimh.local;; 3) h=sia-pi-b.cimh.local;; esac
    put m$m 999 pki/ca.pem mongo_keyfile mongo_root mongo_svc_identity mongo_svc_catalog mongo_svc_inventory mongo_svc_order mongo_svc_backup mongo_svc_monitor mongo_admin_ops
    cp /in/pki/$h.pem /s/m$m/mongo.pem; chown 999 /s/m$m/mongo.pem; chmod 400 /s/m$m/mongo.pem
  done
  put redis 999 redis_users.acl redis_exporter
  put kafka 1000 pki/ca.pem $(cd /in && ls kafka_*)
  cp /in/pki/sia-host.cimh.local.pem /s/kafka/kafka.pem; chown 1000 /s/kafka/kafka.pem; chmod 400 /s/kafka/kafka.pem
  put app 10001 pki/ca.pem $(cd /in && ls mongo_url_* redis_url_* kafka_relay) jwt_private_key data_key code_pepper service_secrets
  for k in relay identity; do cp /in/kafka_$k /s/app/app_kafka_$k; chown 10001 /s/app/app_kafka_$k; chmod 400 /s/app/app_kafka_$k; done
  put backup 999 pki/ca.pem mongo_url_backup mongo_url_restore restic_password'
ok "secrets volume prepared"

echo "== 3. images"
docker build -q -f "$ROOT/services/identity-svc/Dockerfile" -t cimh/identity-svc:rehearsal "$ROOT" >/dev/null
$C --profile tools build -q backup >/dev/null
ok "identity-svc and backup images built"

echo "== 4. MongoDB replica set (deploy/mongo/init-replset.js, roles.js)"
start mongo1 mongo2 mongo3
$C exec -T -e MONGO_MEMBERS=sia-host.cimh.local:27017,sia-pi-a.cimh.local:27017,sia-pi-b.cimh.local:27017 mongo1 \
  mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host localhost --file /dev/stdin < "$ROOT/deploy/mongo/init-replset.js"
$C exec -T -e SECRETS_DIR=/run/secrets mongo1 \
  mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host localhost --file /dev/stdin < "$ROOT/deploy/mongo/roles.js"
rs_state() { mongo_root --eval 'rs.status().members.map(m => m.name.split(".")[0] + "=" + m.stateStr).join(" ")' | tr -d '\r'; }
for _ in $(seq 1 30); do s=$(rs_state); [[ "$s" == *"sia-pi-a=SECONDARY"*"sia-pi-b=SECONDARY"* ]] && break; sleep 2; done
echo "     $s"
check "1 primary (sia-host) + 2 secondaries" grep -q "sia-host=PRIMARY sia-pi-a=SECONDARY sia-pi-b=SECONDARY" <<< "$s"
check "plain (non-TLS) connection refused" bash -c "! $C exec -T mongo1 mongosh --quiet --host localhost --eval 1"
check "anonymous TLS connection cannot read data" bash -c "! $C exec -T mongo1 mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host sia-host.cimh.local --eval 'db.getSiblingDB(\"inventory\").accounts.findOne()'"
svc_try() { # user collection -> exit 0 if an insert works
  $C exec -T mongo1 mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host sia-host.cimh.local \
    -u "svc_$1" -p "$(cat "$SEC/mongo_svc_$1")" --authenticationDatabase admin \
    --eval "db.getSiblingDB('inventory').$2.insertOne({rehearsal: true}).acknowledged ? quit(0) : quit(1)"; }
check "svc_identity may write accounts" svc_try identity accounts
svc_denied() { ! svc_try "$@"; }
check "svc_catalog may NOT write accounts" svc_denied catalog accounts
check "svc_order may NOT write product" svc_denied order product

echo "== 5. Redis (deploy/redis) and Kafka (deploy/kafka/setup.sh)"
start redis
rcli() { $C exec -T redis redis-cli --no-auth-warning --user "$1" --pass "$(cat "$SEC/redis_$1")" "${@:2}" | tr -d '\r'; }
r_ok() { [[ $(rcli identity SET sess:rehearsal 1) == OK ]]; }
r_denied() { rcli catalog GET sess:rehearsal | grep -q NOPERM; }
r_revoked() { ! rcli catalog GET revoked:session:x | grep -q NOPERM; }
check "redis: identity may SET sess:*" r_ok
check "redis: catalog may NOT read sess:*" r_denied
check "redis: catalog may read revoked:*" r_revoked
check "redis: default user disabled" bash -c "$C exec -T redis redis-cli PING | grep -qi 'NOAUTH\|WRONGPASS\|disabled'"
if $C up -d --quiet-pull --wait --wait-timeout 240 kafka1 kafka2 kafka3 >/dev/null 2>&1; then ok "kafka x3 healthy (mTLS)"
else bad "kafka x3 healthy"; $C logs --tail 30 kafka1; exit 1; fi
$C up kafka-setup --exit-code-from kafka-setup >/dev/null 2>&1 && ok "kafka-setup: users, topics, ACLs" || { bad "kafka-setup"; $C logs kafka-setup | tail -20; }
kclient() { # principal command...
  local u=$1; shift
  $C --profile tools run --rm -T kafka-client "cat > /tmp/c.properties <<EOF
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username=\"$u\" password=\"\$(cat /run/secrets/kafka_$u)\";
ssl.truststore.type=PEM
ssl.truststore.location=/run/secrets/ca.pem
EOF
$*" 2>&1; }
topics=$(kclient admin /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka1:9092 --command-config /tmp/c.properties --describe --topic identity.user.events)
check "topic identity.user.events: RF 3, min ISR 2 cluster default" grep -q "ReplicationFactor: 3" <<< "$topics"
denied=$(echo x | kclient catalog "echo x | /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka1:9092 --producer.config /tmp/c.properties --topic identity.user.events --request-required-acks all" || true)
check "kafka: catalog may NOT produce to identity.user.events" grep -q "TopicAuthorizationException\|not authorized" <<< "$denied"
check "kafka: plaintext client rejected" bash -c "! $C --profile tools run --rm -T kafka-client 'timeout 20 /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka1:9092 --list' 2>/dev/null | grep -q identity"

echo "== 6. identity-svc + outbox relay on the platform"
$C up -d --no-deps --wait identity-svc outbox-relay-identity >/dev/null 2>&1 || true
ready() { curl -fsS http://127.0.0.1:18101/health/ready | grep -q '"ok"\|ready\|true'; }
check "identity-svc /health/ready" ready
email="rehearsal-$RANDOM@example.org"
# No `-o /dev/null`: with MSYS_NO_PATHCONV, Windows curl can't open that path. Status is the last line.
code=$(curl -s -w '\n%{http_code}' -X POST http://127.0.0.1:18101/api/identity/v1/auth/register \
  -H 'content-type: application/json' \
  -d "{\"firstname\":\"Re\",\"lastname\":\"Hearsal\",\"email\":\"$email\",\"password\":\"Rehearsal-pass-$RANDOM-x\",\"organisationText\":\"Rehearsal Org\",\"country\":\"BB\"}" | tail -1)
check "register over the real stack (HTTP $code)" test "$code" = 202
events=$(kclient identity "timeout 40 /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka1:9092 --consumer.config /tmp/c.properties --group identity-rehearsal --topic identity.user.events --from-beginning --max-messages 1" || true)
check "relay published user.registered to Kafka (read as principal identity)" grep -q '"user.registered"' <<< "$events"

echo "== 7. failover"
$C stop mongo1 >/dev/null
for _ in $(seq 1 30); do
  p=$($C exec -T mongo2 mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host sia-pi-a.cimh.local -u root -p "$(cat "$SEC/mongo_root")" --authenticationDatabase admin --eval 'db.hello().primary' 2>/dev/null | tr -d '\r' || true)
  [[ "$p" == sia-pi-* ]] && break; sleep 2
done
check "a Pi becomes primary when sia-host stops ($p)" grep -q "sia-pi-" <<< "$p"
$C start mongo1 >/dev/null
for _ in $(seq 1 45); do s=$(rs_state 2>/dev/null || true); [[ "$s" == *"sia-host=PRIMARY"* ]] && break; sleep 2; done
check "sia-host takes primary back (priority 10)" grep -q "sia-host=PRIMARY" <<< "$s"

echo "== 8. backup -> restore -> verify (deploy/backup)"
mongo_root --eval '
  const d = db.getSiblingDB("inventory");
  d.product.insertMany(Array.from({length: 500}, (_, i) => ({ code: "REH" + i, type: "MET", rehearsal: true })));
  d.storage.insertMany(Array.from({length: 300}, (_, i) => ({ barcode: "B" + i, rehearsal: true })));' >/dev/null
if $C --profile tools run --rm -T backup backup.sh; then ok "backup.sh (mongodump --oplog from a secondary -> restic)"; else bad "backup.sh"; fi
start mongo-restore
if $C --profile tools run --rm -T backup restore.sh latest; then ok "restore.sh: every collection count matches the manifest"; else bad "restore.sh"; fi

echo "== 9. resilience (TEST_STRATEGY §7: the parts that run on one host)"
register() { # email -> account id, once the account exists
  curl -s -X POST http://127.0.0.1:18101/api/identity/v1/auth/register -H 'content-type: application/json' \
    -d "{\"firstname\":\"Re\",\"lastname\":\"Silience\",\"email\":\"$1\",\"password\":\"Rehearsal-pass-$RANDOM-x\",\"organisationText\":\"Rehearsal Org\",\"country\":\"BB\"}" >/dev/null
  mongo_root --eval "print(db.getSiblingDB('inventory').accounts.findOne({email: '$1'}).id)" | tr -d '\r'
}
published() { # account id -> 0 if user.registered for it is on Kafka (fresh consumer group, read from the start)
  # A few tries: right after a broker or relay restart the group coordinator can take a while to settle.
  for _ in 1 2 3; do
    out=$(kclient identity "timeout 90 /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka1:9092 --consumer.config /tmp/c.properties --group identity-reh-$RANDOM --topic identity.user.events --from-beginning --timeout-ms 30000" || true); grep -q "$1" <<< "$out" && return 0
  done
  return 1
}
pending() { # account id -> number of events still in its outbox
  mongo_root --eval "print((db.getSiblingDB('inventory').accounts.findOne({id: '$1'}).outbox || []).length)" | tr -d '\r'
}

# (Output is captured before grep -q: with pipefail, grep -q closing the pipe early fails the producer.)
# Exporters: the alert rules need these exact metric names (promtool cannot check names against exporters).
start mongodb-exporter kafka-exporter redis-exporter
scrape() { docker run --rm --network sia-rehearsal_data curlimages/curl:8.11.1 -fsS "http://$1/metrics"; }
has_metric() { for _ in $(seq 1 40); do out=$(scrape "$1" 2>/dev/null || true); grep -q "^$2" <<< "$out" && return 0; sleep 3; done; return 1; }
check "mongodb-exporter: mongodb_rs_members_health (ReplicaSetMemberDown)" has_metric mongodb-exporter:9216 'mongodb_rs_members_health{'
check "kafka-exporter: kafka_topic_partition_current_offset (DlqNotEmpty)" has_metric kafka-exporter:9308 'kafka_topic_partition_current_offset{'
check "kafka-exporter: kafka_consumergroup_lag (ConsumerLagHigh)" has_metric kafka-exporter:9308 'kafka_consumergroup_lag{'
check "redis-exporter: redis_up 1" has_metric redis-exporter:9121 'redis_up 1'
# A Pi down shows as an unhealthy member (alert ReplicaSetMemberDown; TEST_STRATEGY §7 "Stop Pi A").
$C stop mongo2 >/dev/null
member_down() { for _ in $(seq 1 20); do out=$(scrape mongodb-exporter:9216 2>/dev/null || true); grep -Eq '^mongodb_rs_members_health\{.*\} 0$' <<< "$out" && return 0; sleep 3; done; return 1; }
check "Pi A stopped: mongodb_rs_members_health 0 for one member" member_down
$C start mongo2 >/dev/null

# One Kafka broker down: acks=all with min.insync.replicas=2 still succeeds on the other two; nothing is lost.
$C stop kafka3 >/dev/null
id=$(register "kafka-down-$RANDOM@example.org")
for _ in $(seq 1 20); do [[ $(pending "$id") == 0 ]] && break; sleep 2; done
check "one broker down: relay still publishes (outbox drained)" test "$(pending "$id")" = 0
check "one broker down: the event is on Kafka" published "$id"
$C up -d --wait --wait-timeout 180 kafka3 >/dev/null 2>&1 || true

# Outbox relay down: events wait on the document, the service reports the backlog, a restart publishes them.
$C stop outbox-relay-identity >/dev/null
id=$(register "relay-down-$RANDOM@example.org")
sleep 5
check "relay down: event waits on the document" test "$(pending "$id")" -ge 1
backlog() { curl -fsS http://127.0.0.1:18101/metrics | grep -E '^outbox_pending_events\{collection="accounts"' | grep -qv ' 0.0$'; }
check "relay down: identity-svc reports outbox_pending_events > 0 (alert OutboxBacklog)" backlog
$C start outbox-relay-identity >/dev/null
for _ in $(seq 1 30); do [[ $(pending "$id") == 0 ]] && break; sleep 2; done
check "relay restarted: backlog published" test "$(pending "$id")" = 0
check "relay restarted: the event is on Kafka" published "$id"

# Redis restart: revocations survive (AOF, appendfsync everysec: wait over a second before the restart).
check "redis: revocation written" bash -c "[[ \$($C exec -T redis redis-cli --no-auth-warning --user identity --pass \"\$(cat '$SEC/redis_identity')\" SET revoked:session:rehearsal 1 EX 900 | tr -d '\r') == OK ]]"
sleep 2
$C restart redis >/dev/null
for _ in $(seq 1 30); do rcli identity PING 2>/dev/null | grep -q PONG && break; sleep 1; done
check "redis restarted: revocation still there (AOF)" bash -c "[[ \$($C exec -T redis redis-cli --no-auth-warning --user identity --pass \"\$(cat '$SEC/redis_identity')\" EXISTS revoked:session:rehearsal | tr -d '\r') == 1 ]]"
check "redis restarted: identity-svc ready again" bash -c "for i in \$(seq 1 30); do curl -fsS http://127.0.0.1:18101/health/ready | grep -q '\"status\":\"ok\"' && exit 0; sleep 1; done; exit 1"

echo
echo "rehearsal: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
