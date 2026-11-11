#!/usr/bin/env bash
# DR-1 (MIGRATION_PLAN §7) end to end on a throwaway MongoDB (single-node replica set, same image as production).
# Usage: bash tools/migrate/dr1.sh [legacy export dir = db]   (from the repo root; needs Docker and the .venv)
# Output: <export>/v2/report.json, mappings.local.json (git-ignored: personal free text), dr1/verify.{json,md}.
set -euo pipefail
src="${1:-db}"
py="${PYTHON:-.venv/Scripts/python.exe}"
[ -x "$py" ] || py=python3
name=sia-dr1-mongo
port=27099

docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" -p 127.0.0.1:$port:27017 mongo:8.0.30 --replSet rs0 --bind_ip_all >/dev/null
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
for _ in $(seq 1 60); do
  docker exec "$name" mongosh --quiet --eval 'try { rs.status().ok } catch (e) { rs.initiate({_id: "rs0", members: [{_id: 0, host: "localhost:27017"}]}).ok }' 2>/dev/null | grep -q 1 && break
  sleep 1
done
for _ in $(seq 1 30); do
  docker exec "$name" mongosh --quiet --eval 'db.hello().isWritablePrimary' 2>/dev/null | grep -q true && break
  sleep 1
done

start=$(date +%s)
"$py" tools/migrate/legacy_to_v2.py "$src" "$src/v2"
"$py" tools/migrate/dr1.py --legacy "$src" --v2 "$src/v2" --uri "mongodb://localhost:$port/?directConnection=true"
echo "DR-1 took $(( $(date +%s) - start )) s; report: $src/v2/dr1/verify.md"
