#!/usr/bin/env bash
# Cut-over G1 + G2 (docs/runbooks/CUTOVER.md): load legacy_to_v2.py output into PRODUCTION rs0, then check counts.
# Run ON sia-host from the deploy directory (where compose.prod.yml and secrets/ live):
#   bash load_prod.sh <dir with the legacy_to_v2.py output>            # refuses if accounts already exist
#   bash load_prod.sh <dir> --replace                                  # wipe and reload (dry runs, no-go retry)
#   bash load_prod.sh <dir> --verify-only                              # just the count check (G2)
# Before anything is written, the current database is dumped to $BACKUPS. The mongo container's root fs is
# read-only, so files and credentials go in over stdin; the root password never appears on a command line.
set -euo pipefail
SRC=${1:?import dir}; MODE=${2:-}
DEPLOY=${DEPLOY:-$PWD}
SECRETS=${SECRETS:-$DEPLOY/secrets}
BACKUPS=${BACKUPS:-/srv/sia-backups/cutover}
P="docker compose -p ${PROJECT:-sia-prod} -f ${COMPOSE_FILE:-$DEPLOY/compose.prod.yml}"
MONGO=${MONGO_CONTAINER:-sia-prod-mongo1-1}
HOST=${MONGO_SELF:-sia-host.cimh.local}
COLLECTIONS="accounts organisations misc product storage stock history orders"
[ -f "$SECRETS/mongo_root" ] || { echo "no $SECRETS/mongo_root (run from the deploy dir or set SECRETS)" >&2; exit 2; }
for c in $COLLECTIONS; do [ -f "$SRC/$c.json" ] || { echo "missing $SRC/$c.json" >&2; exit 2; }; done

# Tool config with the password, written into the container's tmpfs and removed on exit.
CONF=/tmp/cutover-tools.yml
printf 'password: "%s"\n' "$(cat "$SECRETS/mongo_root")" | docker exec -i "$MONGO" sh -c "umask 077; cat > $CONF"
trap 'docker exec "$MONGO" rm -f "$CONF" >/dev/null 2>&1 || true' EXIT
TOOL_ARGS="--host $HOST --tls --tlsCAFile /run/secrets/ca.pem --username root --authenticationDatabase admin --config $CONF"
msh() {  # mongosh as root on inventory; script on stdin after an auth prologue
  { printf 'db.getSiblingDB("admin").auth("root", %s);\n' "$(sed 's/\\/\\\\/g; s/"/\\"/g; s/.*/"&"/' "$SECRETS/mongo_root")"; cat; } |
    docker exec -i "$MONGO" mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host "$HOST" inventory
}

verify() {
  local fail=0
  for c in $COLLECTIONS; do
    docker exec -i "$MONGO" sh -c 'umask 077; cat > /tmp/count.json' < "$SRC/$c.json"
    want=$(docker exec "$MONGO" mongosh --quiet --nodb --eval \
      'print(EJSON.parse(fs.readFileSync("/tmp/count.json", "utf8")).length)'; docker exec "$MONGO" rm -f /tmp/count.json)
    got=$(echo "print(db.$c.countDocuments({}))" | msh | tail -1)
    [ "$want" = "$got" ] && r=PASS || { r=FAIL; fail=1; }
    printf '%-14s file %6s  db %6s  %s\n' "$c" "$want" "$got" "$r"
  done
  echo 'const v = db.getCollectionInfos().filter(c => c.options.validator).map(c => c.name + ":" + c.options.validationLevel + "/" + c.options.validationAction);
        print("validators", v.join(" "));
        print("stock==product", db.stock.countDocuments({}) === db.product.countDocuments({}));
        print("xuser view", db.getCollectionInfos({name: "xuser"}).length === 1);' | msh
  return $fail
}

if [ "$MODE" = "--verify-only" ]; then verify; exit; fi

existing=$(echo 'print(db.accounts.countDocuments({}))' | msh | tail -1)
if [ "$existing" != "0" ] && [ "$MODE" != "--replace" ]; then
  echo "production already holds $existing accounts; refusing (use --replace only for a dry run or a no-go retry)" >&2
  exit 1
fi

mkdir -p "$BACKUPS" && chmod 700 "$BACKUPS"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker exec "$MONGO" mongodump $TOOL_ARGS --quiet --db inventory --archive --gzip > "$BACKUPS/pre-load-$stamp.archive.gz"
chmod 600 "$BACKUPS/pre-load-$stamp.archive.gz"
echo "backup: $BACKUPS/pre-load-$stamp.archive.gz"

APPS=$($P config --services | grep -vE '^(mongo1|redis|kafka[0-9]*|kafka-setup|nginx|certbot|prometheus|alertmanager|.*-exporter|clamav)$' || true)
echo "stopping app services"; $P stop $APPS >/dev/null

echo 'for (const c of ["accounts","organisations","misc","product","storage","stock","history","orders","temp","auditlog","xuser"]) {
        if (db.getCollectionNames().includes(c)) db[c].drop(); }' | msh >/dev/null
for c in $COLLECTIONS; do
  docker exec -i "$MONGO" mongoimport $TOOL_ARGS --quiet --db inventory --collection "$c" --jsonArray < "$SRC/$c.json"
done

# Caches, idempotency keys and revocations refer to the old data.
# Production Redis has no user allowed FLUSHALL (ACL per service), so empty its data dir while apps are down.
REDIS_DATA=${REDIS_DATA:-/srv/redis}
$P stop redis >/dev/null
find "$REDIS_DATA" -mindepth 1 -delete
$P up -d redis >/dev/null

echo "starting app services (they create indexes, validators and the xuser view)"; $P up -d $APPS >/dev/null
for _ in $(seq 1 30); do
  [ "$(echo 'print(db.getCollectionInfos({name:"xuser"}).length)' | msh | tail -1)" = "1" ] && break; sleep 5
done
verify
