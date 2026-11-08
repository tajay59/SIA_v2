#!/usr/bin/env bash
# Replace the staging-lite database with migrated legacy data (demo production).
# Run ON kw-server: bash load_staging.sh <dir with the legacy_to_v2.py output>
# Keeps a gzip dump of the previous database in /opt/sia-staging/backups first.
set -euo pipefail
SRC=${1:?import dir}
STACK=/opt/sia-staging
P="docker compose -p sia-staging -f $STACK/compose.yml"
MONGO=sia-staging-mongo-1
COLLECTIONS="accounts organisations misc product storage stock history orders"
APPS=$($P config --services | grep -vE '^(mongo|redis|kafka|gateway|kafka-setup|mongo-init)$' || true)

mkdir -p "$STACK/backups" && chmod 700 "$STACK/backups"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker exec "$MONGO" mongodump --quiet --db inventory --archive --gzip > "$STACK/backups/pre-migration-$stamp.archive.gz"
echo "backup: $STACK/backups/pre-migration-$stamp.archive.gz"

echo "stopping app services"; $P stop $APPS >/dev/null

docker exec "$MONGO" mongosh --quiet inventory --eval '
  for (const c of ["accounts","organisations","misc","product","storage","stock","history","orders","temp","auditlog","xuser"]) {
    if (db.getCollectionNames().includes(c)) db[c].drop();
  }'
docker exec "$MONGO" mkdir -p /tmp/import
for c in $COLLECTIONS; do
  docker cp "$SRC/$c.json" "$MONGO:/tmp/import/$c.json"
  docker exec "$MONGO" mongoimport --quiet --db inventory --collection "$c" --jsonArray --file "/tmp/import/$c.json"
done
docker exec "$MONGO" rm -rf /tmp/import

# Caches/idempotency/revocations refer to the old data.
docker exec sia-staging-redis-1 redis-cli FLUSHALL >/dev/null

echo "starting app services (they create indexes and the xuser view)"; $P up -d $APPS >/dev/null
sleep 20
docker exec "$MONGO" mongosh --quiet inventory --eval '
  db.getCollectionNames().sort().forEach(c => print(c, db[c].countDocuments()))'
$P ps --format '{{.Service}} {{.Status}}'
