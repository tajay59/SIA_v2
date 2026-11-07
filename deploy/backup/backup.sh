#!/usr/bin/env bash
# Nightly MongoDB backup (INFRASTRUCTURE §7): mongodump --oplog from a secondary, streamed into restic,
# plus a manifest of per-collection counts that restore.sh checks against. Retention 30 daily + 12 monthly.
#   env: MONGO_URI[_FILE], RESTIC_REPOSITORY, RESTIC_PASSWORD_FILE, METRICS_DIR (optional)
set -euo pipefail
URI=${MONGO_URI:-$(cat "${MONGO_URI_FILE:?MONGO_URI or MONGO_URI_FILE}")}
TAG=${BACKUP_TAG:-$(date -u +%Y%m%dT%H%M%SZ)}
start=$(date +%s)

restic snapshots >/dev/null 2>&1 || restic init

# 1. Manifest first: counts at (roughly) dump time. The oplog makes the dump consistent; counts may differ
#    by writes during the dump, so restore.sh compares with a tolerance only where writes are expected.
mongosh "$URI" --quiet --eval '
  const d = db.getSiblingDB("inventory"); const out = {};
  d.getCollectionInfos({ type: "collection" }).forEach(c => out[c.name] = d.getCollection(c.name).estimatedDocumentCount());
  print(JSON.stringify(out));' > /tmp/manifest.json
restic backup --stdin --stdin-filename manifest.json --tag mongo --tag "run-$TAG" < /tmp/manifest.json >/dev/null

# 2. The dump itself, never written to local disk.
mongodump --uri "$URI" --readPreference=secondaryPreferred --oplog --archive --gzip --quiet \
  | restic backup --stdin --stdin-filename mongo.archive.gz --tag mongo --tag "run-$TAG"
# A failed mongodump must fail the run even though restic got a (truncated) stream.
[[ ${PIPESTATUS[0]} -eq 0 ]] || { echo "mongodump failed" >&2; exit 1; }

# 3. Retention and a light integrity check (full `restic check --read-data` runs monthly by cron on the target).
restic forget --tag mongo --group-by paths --keep-daily 30 --keep-monthly 12 --prune --quiet || true
restic check --quiet

end=$(date +%s)
echo "backup $TAG ok in $((end-start))s"
if [[ -n "${METRICS_DIR:-}" ]]; then
  printf 'sia_backup_last_success_timestamp_seconds %s\nsia_backup_duration_seconds %s\n' "$end" "$((end-start))" \
    > "$METRICS_DIR/backup.prom.tmp" && mv "$METRICS_DIR/backup.prom.tmp" "$METRICS_DIR/backup.prom"
fi
