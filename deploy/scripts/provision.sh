#!/usr/bin/env bash
# First build of the platform on sia-host (INFRASTRUCTURE §10 steps 4-8). Run as root (ops + sudo) from the
# repository's deploy/ directory after bootstrap, once both Pis run compose.pi.yml. Every step is
# idempotent, so a failed run can simply be repeated. The same sequence runs end to end, on one Docker
# host, in tools/infra/rehearsal/run.sh (CI job `rehearsal`).
#
#   VLAN_IP=10.x.y.10 deploy/scripts/provision.sh
set -euo pipefail
DEPLOY=$(cd "$(dirname "$0")/.." && pwd)
SEC="$DEPLOY/secrets"
cd "$DEPLOY"
: "${VLAN_IP:?VLAN IP of sia-host}"

echo "== step 4: private CA, secrets, Redis ACL"
bash pki/make-certs.sh "$SEC/pki"
bash scripts/make-secrets.sh "$SEC"
bash redis/render-acl.sh "$SEC"
[[ -s "$SEC/smtp_password" ]] || { echo "put the SMTP (Gmail app) password in $SEC/smtp_password first" >&2; exit 1; }
# Compose (non-swarm) bind-mounts secret files with their host owner and mode: give each file to the uid
# of the container that reads it. Kafka (1000) and mongod (999) both use the host cert: one copy each.
[[ -s "$SEC/pki/kafka-broker.pem" ]] || cp "$SEC/pki/sia-host.cimh.local.pem" "$SEC/pki/kafka-broker.pem"
chown 999 "$SEC/mongo_keyfile" "$SEC/redis_users.acl" "$SEC/redis_exporter" "$SEC/pki/sia-host.cimh.local.pem"
chown 1000 "$SEC/pki/kafka-broker.pem" "$SEC"/kafka_*
# kafka-setup (uid 1000) reads every Kafka password; services (uid 10001) read their own from a copy.
for k in relay identity catalog inventory order document notification media; do install -m 400 -o 10001 "$SEC/kafka_$k" "$SEC/app_kafka_$k"; done
chown 10001 "$SEC"/mongo_url_* "$SEC"/redis_url_* "$SEC/jwt_private_key" "$SEC/data_key" "$SEC/code_pepper" \
  "$SEC/service_secrets" "$SEC"/service_secret_*
chmod 444 "$SEC/pki/ca.pem"
echo "   -> copy new secrets (and pki/ca.key, then delete it here) into the CIMH password manager"

[[ -s "$SEC/kafka_cluster_id" ]] || docker run --rm --entrypoint /opt/kafka/bin/kafka-storage.sh \
  apache/kafka:3.9.0 random-uuid > "$SEC/kafka_cluster_id"
KAFKA_CLUSTER_ID=$(cat "$SEC/kafka_cluster_id")
export KAFKA_CLUSTER_ID VLAN_IP
export HELLO_SVC_DIGEST=${HELLO_SVC_DIGEST:-unset} IDENTITY_SVC_DIGEST=${IDENTITY_SVC_DIGEST:-unset} \
  CATALOG_SVC_DIGEST=${CATALOG_SVC_DIGEST:-unset} MEDIA_WORKER_DIGEST=${MEDIA_WORKER_DIGEST:-unset} \
  INVENTORY_SVC_DIGEST=${INVENTORY_SVC_DIGEST:-unset} \
  ORDER_SVC_DIGEST=${ORDER_SVC_DIGEST:-unset} \
  DOCUMENT_SVC_DIGEST=${DOCUMENT_SVC_DIGEST:-unset} \
  NOTIFICATION_SVC_DIGEST=${NOTIFICATION_SVC_DIGEST:-unset}
mkdir -p /srv/mongo /srv/redis /srv/kafka/1 /srv/kafka/2 /srv/kafka/3 /srv/prometheus /srv/sia-data
chown 999 /srv/mongo /srv/redis
chown 1000 /srv/kafka/1 /srv/kafka/2 /srv/kafka/3
chown 65534 /srv/prometheus
# Files volume (INFRASTRUCTURE §5): services write as 10001; nginx serves products/ read-only.
mkdir -p /srv/sia-data/incoming /srv/sia-data/public/products /srv/sia-data/protected /srv/sia-data/quarantine
chown 10001 /srv/sia-data /srv/sia-data/incoming /srv/sia-data/public /srv/sia-data/public/products /srv/sia-data/protected /srv/sia-data/quarantine
C="docker compose -f compose.prod.yml"

echo "== step 5: replica set (the Pis must already run compose.pi.yml)"
$C up -d --wait mongo1
mongo_local() { $C exec -T mongo1 mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host localhost --file /dev/stdin; }
mongo_local < mongo/init-replset.js
# roles.js needs the user passwords, but mongo1 only mounts its own cert and keyfile. Prepend them as a JS
# object on stdin (never written inside the container, never in argv); first run uses the localhost exception.
{
  printf 'const SECRETS = {'
  for f in mongo_root mongo_svc_identity mongo_svc_catalog mongo_svc_inventory mongo_svc_order mongo_svc_backup mongo_admin_ops; do
    printf '%s: %s, ' "$f" "$(python3 -c 'import json, sys; print(json.dumps(open(sys.argv[1]).read().strip()))' "$SEC/$f")"
  done
  printf '};\n'
  cat mongo/roles.js
} | mongo_local
$C exec -T mongo1 mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host sia-host.cimh.local \
  -u root -p "$(cat "$SEC/mongo_root")" --authenticationDatabase admin \
  --eval 'rs.status().members.forEach(m => print("   ", m.name, m.stateStr))'

echo "== step 6: Kafka (SCRAM users, topics, ACLs) and Redis"
$C up -d --wait kafka1 kafka2 kafka3 redis
$C up kafka-setup --exit-code-from kafka-setup

echo "== steps 7-8: monitoring (services and nginx arrive with their first deploy.sh run)"
scripts/render-config.sh prod
$C up -d --wait prometheus alertmanager node-exporter
echo "provisioned. Next: deploy.sh per service; then step 9: backups on Pi B and a restore into staging."
