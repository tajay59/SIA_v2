#!/usr/bin/env bash
# Deploy staging-lite to the shared demo server. Run from the repository root on a machine with `ssh kw-server` access:
#
#   deploy/staging-lite/deploy.sh            # build image, ship it, (re)start the stack
#   deploy/staging-lite/deploy.sh --edge     # also install the edge site + certificate (first time)
#
# Safe on a shared box: touches only /opt/sia-staging, the compose project `sia-staging`, the file
# /srv/edge-sites/cimh-stores-staging.conf and the certificate sia.hashiz.store. The edge nginx is
# tested (nginx -t) before every reload and the previous edge file is restored if the test fails.
set -euo pipefail
export MSYS_NO_PATHCONV=1

HOST=${HOST:-kw-server}
DIR=/opt/sia-staging
TAG=staging
EDGE=0; [[ "${1:-}" == "--edge" ]] && EDGE=1
HERE=$(cd "$(dirname "$0")" && pwd)

echo "== build image"
docker build -q -f services/identity-svc/Dockerfile --build-arg APP_VERSION="$(git rev-parse --short HEAD)" \
  -t cimh/identity-svc:$TAG . >/dev/null

echo "== ship image ($(docker image inspect cimh/identity-svc:$TAG --format '{{.Size}}' | awk '{printf "%d MB", $1/1e6}'))"
docker save cimh/identity-svc:$TAG | gzip -1 | ssh "$HOST" 'gunzip | docker load -q'

echo "== copy stack files"
ssh "$HOST" "mkdir -p $DIR/site $DIR/secrets && chmod 700 $DIR/secrets"
scp -q "$HERE/compose.yml" "$HERE/gateway.conf" "$HERE/proxy.inc" "$HERE/edge-site.conf" "$HERE/edge-site-http.conf"   "$HERE/../kafka/create-topics.sh" "$HOST:$DIR/"
scp -q -r "$HERE/site/." "$HOST:$DIR/site/"

echo "== secrets (created once, never overwritten, never leave the server)"
ssh "$HOST" bash -s <<'EOF'
set -euo pipefail
cd /opt/sia-staging/secrets
umask 077
[ -s jwt_private_key.pem ] || openssl genpkey -algorithm ed25519 -out jwt_private_key.pem
[ -s data_key ] || openssl rand -base64 32 | tr -d '\n' > data_key
[ -s code_pepper ] || openssl rand -base64 32 | tr -d '\n' > code_pepper
[ -s service_secrets ] || printf 'notification=%s\norder=%s\ncatalog=%s\ninventory=%s\ndocument=%s\nmedia=%s\n' \
  "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" \
  "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" > service_secrets
# Containers run as uid 10001 and read the secrets via bind mounts.
chown 10001 jwt_private_key.pem data_key code_pepper service_secrets
chmod 400 jwt_private_key.pem data_key code_pepper service_secrets
EOF

echo "== start stack"
ssh "$HOST" "cd $DIR && docker compose up -d --wait --wait-timeout 240 2>&1 | tail -5"

if [[ $EDGE == 1 ]]; then
  echo "== edge site + certificate"
  ssh "$HOST" bash -s <<'EOF'
set -euo pipefail
SITE=/srv/edge-sites/cimh-stores-staging.conf
CERT=/etc/letsencrypt/live/sia.hashiz.store
reload_or_restore() {
  if docker exec printit-nginx nginx -t >/tmp/sia-nginx-test.log 2>&1; then
    docker exec printit-nginx nginx -s reload
  else
    echo "edge config test FAILED; restoring"; cat /tmp/sia-nginx-test.log
    if [ -f "$SITE.bak" ]; then mv "$SITE.bak" "$SITE"; else rm -f "$SITE"; fi
    docker exec printit-nginx nginx -t && docker exec printit-nginx nginx -s reload
    exit 1
  fi
}
[ -f "$SITE" ] && cp "$SITE" "$SITE.bak"
if [ ! -d "$CERT" ]; then
  # Phase 1: HTTP only (ACME challenge), so the cert can be issued without stopping the edge.
  cp /opt/sia-staging/edge-site-http.conf "$SITE"
  reload_or_restore
  certbot certonly --webroot -w /srv/edge-sites/acme -d sia.hashiz.store -d store.hashiz.store \
    --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring \
    --deploy-hook "docker exec printit-nginx nginx -s reload"
fi
cp /opt/sia-staging/edge-site.conf "$SITE"
reload_or_restore
rm -f "$SITE.bak"
EOF
fi

echo "== status"
ssh "$HOST" "cd $DIR && docker compose ps --format '{{.Service}}: {{.Status}}'"
