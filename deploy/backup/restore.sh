#!/usr/bin/env bash
# Restore a MongoDB backup from restic into a target (staging for the quarterly restore test; a new primary in
# DR), then verify every collection count against the backup's manifest (INFRASTRUCTURE §7, §12).
#   restore.sh [run-tag|latest]
#   env: TARGET_URI[_FILE] (needs the restore role), RESTIC_REPOSITORY, RESTIC_PASSWORD_FILE, DROP=1 to replace
# Exit 0 only if every collection in the manifest is present with the same count.
set -euo pipefail
WHICH=${1:-latest}
TARGET=${TARGET_URI:-$(cat "${TARGET_URI_FILE:?TARGET_URI or TARGET_URI_FILE}")}

if [[ "$WHICH" == latest ]]; then
  WHICH=$(restic snapshots --tag mongo --compact | grep -o 'run-[0-9TZ]*' | sort | tail -1)
fi
[[ "$WHICH" == run-* ]] || WHICH="run-$WHICH"
echo "restoring $WHICH"

restic dump --tag "mongo,$WHICH" --path /manifest.json latest manifest.json > /tmp/manifest.json
restic dump --tag "mongo,$WHICH" --path /mongo.archive.gz latest mongo.archive.gz \
  | mongorestore --uri "$TARGET" --archive --gzip --oplogReplay --bypassDocumentValidation ${DROP:+--drop} --quiet

# Verify counts.
mongosh "$TARGET" --quiet --eval '
  const want = JSON.parse(require("fs").readFileSync("/tmp/manifest.json", "utf8"));
  const d = db.getSiblingDB("inventory"); let bad = 0;
  for (const [name, n] of Object.entries(want)) {
    const got = d.getCollection(name).countDocuments({});
    const ok = got === n;
    if (!ok) bad++;
    print(`${ok ? "ok  " : "BAD "} ${name}: backup ${n}, restored ${got}`);
  }
  if (bad) { print(`${bad} collection(s) differ`); quit(1); }
  print("restore verified");'
