#!/usr/bin/env bash
# Cut-over G3 (docs/runbooks/CUTOVER.md): load files_to_v2.py output into PRODUCTION.
# Run ON sia-host from the deploy directory, after load_prod.sh:  bash load_files_prod.sh <dir with media/ and apply.js>
# Copies media/ into /srv/sia-data (app user 10001; protected files 0644 so the edge nginx can serve them through
# X-Accel-Redirect: /_protected/ is internal), scans protected/ with ClamAV, then attaches the records.
set -euo pipefail
SRC=${1:?dir}
DEPLOY=${DEPLOY:-$PWD}
SECRETS=${SECRETS:-$DEPLOY/secrets}
DATA=${DATA_DIR:-/srv/sia-data}
MONGO=${MONGO_CONTAINER:-sia-prod-mongo1-1}
HOST=${MONGO_SELF:-sia-host.cimh.local}
[ -d "$SRC/media" ] && [ -f "$SRC/apply.js" ] || { echo "need $SRC/media and $SRC/apply.js" >&2; exit 2; }

docker run --rm -v "$DATA:/srv/sia-data" -v "$(cd "$SRC" && pwd)/media:/in:ro" alpine:3.20 sh -c \
  'cp -R /in/. /srv/sia-data/ && chown -R 10001:10001 /srv/sia-data/public /srv/sia-data/protected &&
   find /srv/sia-data/public /srv/sia-data/protected -type d -exec chmod 755 {} + &&
   find /srv/sia-data/public /srv/sia-data/protected -type f -exec chmod 644 {} +'

# Legacy uploads never went through ClamAV: scan before anyone can download them.
# The clamd container doesn't mount the data dir, so a one-off clamscan uses its signature databases (needs ~1.5 GB
# RAM for a minute: run it before the go/no-go, not under load).
docker run --rm --network none -v "${CLAMAV_DB:-/srv/clamav}:/var/lib/clamav:ro" -v "$DATA/protected:/scan:ro" \
  --entrypoint clamscan clamav/clamav:1.4 -r --infected --no-summary /scan \
  && echo "clamav: 0 infected" \
  || { echo "clamav found infected files (listed above) or failed: resolve before go-live" >&2; exit 1; }

{ printf 'db.getSiblingDB("admin").auth("root", %s);\n' "$(sed 's/\\/\\\\/g; s/"/\\"/g; s/.*/"&"/' "$SECRETS/mongo_root")"; cat "$SRC/apply.js"; } |
  docker exec -i "$MONGO" mongosh --quiet --tls --tlsCAFile /run/secrets/ca.pem --host "$HOST" inventory
