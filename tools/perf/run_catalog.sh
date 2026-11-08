#!/usr/bin/env bash
# Catalogue performance check on the DEV stack (IMPLEMENTATION_PLAN P3 exit: catalogue p95 < 300 ms on seeded
# data; TRD TR-DATA-5 explain check). Run from the repo root with the dev stack up:
#
#   tools/perf/run_catalog.sh                     # seed 200k, explain, steady 50 req/s for 3 min, keep data
#   PRODUCTS=500000 RATE=80 tools/perf/run_catalog.sh
#   MODE=knee tools/perf/run_catalog.sh           # ramp to find the knee (no gate)
#   CLEANUP=1 tools/perf/run_catalog.sh           # also remove the perf products at the end
#
# Results: tools/perf/results/catalog-<mode>-<timestamp>.json (git-ignored).
set -euo pipefail

NET=${NET:-sia-dev_default}
IMAGE=${IMAGE:-cimh/catalog-svc:dev}
K6=${K6:-grafana/k6:1.3.0}
MONGO=${MONGO:-mongodb://mongo:27017/?replicaSet=rs0}
PRODUCTS=${PRODUCTS:-200000}
MODE=${MODE:-steady}

export MSYS_NO_PATHCONV=1
ROOT=$(pwd -W 2>/dev/null || pwd)
mkdir -p tools/perf/results
OUT="catalog-${MODE}-$(date +%Y%m%d-%H%M%S).json"
py() { docker run --rm --network "$NET" -v "$ROOT/tools:/w/tools:ro" "$IMAGE" python "$@"; }

if ! py /w/tools/perf/seed_catalog.py --mongo "$MONGO" --products "$PRODUCTS"; then
  echo "(perf products already seeded; reusing them)"
fi
py /w/tools/perf/explain_catalog.py --mongo "$MONGO"
TOKEN=$(py /w/tools/perf/staff_token.py --mongo "$MONGO")

status=0
docker run --rm --network "$NET" --cpus 4 -v "$ROOT/tools/perf:/perf" \
  -e MODE="$MODE" -e RATE="${RATE:-50}" -e MAX_RATE="${MAX_RATE:-400}" -e DURATION="${DURATION:-}" \
  -e STAFF_TOKEN="$TOKEN" "$K6" run --quiet --summary-export "/perf/results/$OUT" /perf/catalog.k6.js || status=$?

if [[ "${CLEANUP:-0}" == 1 ]]; then py /w/tools/perf/seed_catalog.py --mongo "$MONGO" --cleanup; fi
echo "summary: tools/perf/results/$OUT (k6 exit $status)"
exit "$status"
