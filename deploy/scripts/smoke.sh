#!/usr/bin/env bash
# Post-deploy smoke test: readiness from inside the container network.
set -euo pipefail
ENVIRONMENT=${1:?env}; SERVICE=${2:?service}
DEPLOY_DIR=$(cd "$(dirname "$0")/.." && pwd)
docker compose -f "$DEPLOY_DIR/compose.${ENVIRONMENT}.yml" exec -T "$SERVICE" \
  python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5).status==200 else 1)"
echo "smoke ok: $SERVICE ($ENVIRONMENT)"
