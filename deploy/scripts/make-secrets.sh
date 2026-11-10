#!/usr/bin/env bash
# Create every Docker secret file that does not exist yet (INFRASTRUCTURE §6). Idempotent: never overwrites.
# The source of record is the CIMH password manager: after the first run, copy each new value there.
#
#   deploy/scripts/make-secrets.sh [secrets-dir]
#
# Generated: random passwords per Mongo/Kafka/Redis principal, the Mongo replica-set keyfile, the identity
# EdDSA signing key and the AES envelope key. Not generated (must be supplied): smtp_password.
set -euo pipefail

DIR=${1:-$(cd "$(dirname "$0")/.." && pwd)/secrets}
mkdir -p "$DIR"; chmod 700 "$DIR"
umask 077

rand() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-40; }
make() { # name generator...
  local f="$DIR/$1"; shift
  if [[ -s "$f" ]]; then return 0; fi
  "$@" > "$f"; chmod 400 "$f"; echo "created $(basename "$f")"
}

# MongoDB: root admin, per-service users (roles.js), backup, read-only ops.
for u in mongo_root mongo_svc_identity mongo_svc_catalog mongo_svc_inventory mongo_svc_order mongo_svc_backup mongo_admin_ops; do
  make "$u" rand
done
make mongo_keyfile sh -c 'openssl rand -base64 756 | tr -d "\n"'

# Kafka SCRAM principals (one per producer/consumer service, TR-SEC-7).
for u in kafka_admin kafka_identity kafka_catalog kafka_inventory kafka_order kafka_document kafka_notification kafka_media kafka_relay kafka_exporter; do
  make "$u" rand
done

# Redis ACL users (users.acl is rendered from these by render-redis-acl.sh).
for u in redis_identity redis_catalog redis_inventory redis_order redis_document redis_notification redis_media redis_relay redis_exporter; do
  make "$u" rand
done

# identity-svc keys (names match JWT_PRIVATE_KEY_FILE, DATA_KEY_FILE, CODE_PEPPER_FILE, SERVICE_SECRETS_FILE)
make jwt_private_key openssl genpkey -algorithm ed25519
make data_key sh -c 'openssl rand -base64 32 | tr -d "\n"'
make code_pepper rand
make service_secrets sh -c 'for s in notification order catalog inventory document media; do echo "$s=$(openssl rand -hex 24)"; done'
# identity-svc reads the whole list; each calling service reads only its own line (SERVICE_SECRET_FILE).
while IFS='=' read -r name value; do
  [[ -n $name ]] || continue
  f="$DIR/service_secret_$name"; rm -f "$f"; printf '%s' "$value" > "$f"; chmod 400 "$f"
done < "$DIR/service_secrets"

# Connection URLs with credentials are secrets too (MONGO_URL_FILE / REDIS_URL_FILE). Re-rendered every run.
MONGO_HOSTS=${MONGO_HOSTS:-sia-host.cimh.local:27017,sia-pi-a.cimh.local:27017,sia-pi-b.cimh.local:27017}
MONGO_OPTS=${MONGO_OPTS:-replicaSet=rs0&tls=true&tlsCAFile=/run/secrets/ca.pem&w=majority&retryWrites=true&maxPoolSize=50}
REDIS_HOST=${REDIS_HOST:-redis:6379}
BACKUP_HOST=${BACKUP_HOST:-sia-pi-b.cimh.local:27017}
url() { local f="$DIR/$1"; rm -f "$f"; printf '%s' "$2" > "$f"; chmod 400 "$f"; }
for svc in identity catalog inventory order; do
  url "mongo_url_$svc" "mongodb://svc_$svc:$(cat "$DIR/mongo_svc_$svc")@$MONGO_HOSTS/inventory?authSource=admin&$MONGO_OPTS"
done
url mongo_url_backup "mongodb://svc_backup:$(cat "$DIR/mongo_svc_backup")@$BACKUP_HOST/?authSource=admin&tls=true&tlsCAFile=/run/secrets/ca.pem&directConnection=true"
for svc in identity catalog inventory order document notification media relay; do
  url "redis_url_$svc" "redis://$svc:$(cat "$DIR/redis_$svc")@$REDIS_HOST/0"
done

# restic repository password (also stored in the password manager; without it backups are unreadable).
make restic_password rand

[[ -s "$DIR/smtp_password" ]] || echo "NOTE: put the SMTP (Gmail app) password in $DIR/smtp_password"
echo "secrets ready in $DIR"
