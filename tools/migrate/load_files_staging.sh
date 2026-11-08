#!/usr/bin/env bash
# Run ON kw-server after files_to_v2.py: bash load_files_staging.sh <dir with media/ and apply.js>
# Copies media/ into the staging media volume (owned by the app user 10001) and attaches the records.
set -euo pipefail
SRC=${1:?dir}
docker run --rm -v sia-staging_media:/srv/sia-data -v "$SRC/media:/in:ro" alpine:3.20 sh -c \
  'cp -R /in/. /srv/sia-data/ && chown -R 10001:10001 /srv/sia-data/public /srv/sia-data/protected &&
   find /srv/sia-data/public /srv/sia-data/protected -type d -exec chmod 755 {} + &&
   find /srv/sia-data/public -type f -exec chmod 644 {} + && find /srv/sia-data/protected -type f -exec chmod 640 {} +'
docker cp "$SRC/apply.js" sia-staging-mongo-1:/tmp/apply.js
docker exec sia-staging-mongo-1 mongosh --quiet inventory /tmp/apply.js
docker exec sia-staging-mongo-1 rm -f /tmp/apply.js
