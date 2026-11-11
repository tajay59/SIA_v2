#!/usr/bin/env bash
# Render the production edge templates with test names and a throwaway certificate, then `nginx -t`.
# Everything happens inside one container (no files on the host). Used by CI (job infra) and before every
# change to deploy/nginx/.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash: keep container paths as written
here=$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))
docker run --rm \
  -e SIA_HOST=sia.test -e STORE_HOST=store.test -e OPS_ALLOW_CIDR=10.0.0.0/8 \
  -e NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d \
  --add-host identity-svc:127.0.0.1 --add-host catalog-svc:127.0.0.1 --add-host inventory-svc:127.0.0.1 \
  --add-host order-svc:127.0.0.1 --add-host document-svc:127.0.0.1 --add-host prometheus:127.0.0.1 \
  -v "$here/templates:/etc/nginx/templates:ro" -v "$here/snippets:/etc/nginx/snippets:ro" \
  nginx:1.27-alpine sh -ec '
    apk add --no-cache -q openssl >/dev/null
    mkdir -p /etc/letsencrypt/live/sia.test /run/secrets
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj "/CN=sia.test" \
      -keyout /etc/letsencrypt/live/sia.test/privkey.pem -out /etc/letsencrypt/live/sia.test/fullchain.pem 2>/dev/null
    echo "ops:x" > /run/secrets/ops_htpasswd
    /docker-entrypoint.sh nginx -t'
