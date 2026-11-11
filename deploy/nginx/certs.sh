#!/usr/bin/env bash
# First certificate for the production edge (INFRASTRUCTURE §3.2, §10). Run once on sia-host from deploy/,
# after DNS for both names points at the host and ports 80/443 are open:
#
#   bash nginx/certs.sh            # uses SIA_HOST, STORE_HOST, CERT_EMAIL from env/prod.env
#
# nginx cannot start without a certificate, and certbot needs nginx to answer the HTTP-01 challenge, so:
# 1) a throwaway self-signed certificate lets nginx start; 2) certbot replaces it with the real one (one
# certificate for both names); 3) nginx reloads. Renewal afterwards is automatic (certbot service, 12 h loop;
# nginx reloads every 6 h). Never run this against an existing real certificate unless it must be replaced.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . env/prod.env; set +a
: "${SIA_HOST:?}" "${STORE_HOST:?}" "${CERT_EMAIL:?}"
C="docker compose -f compose.prod.yml"
LE=${LETSENCRYPT_DIR:-/srv/letsencrypt}
live="$LE/live/$SIA_HOST"

if [[ -f "$live/fullchain.pem" ]] && ! grep -q "dummy" "$live/.source" 2>/dev/null; then
  echo "certificate for $SIA_HOST already present: nothing to do (certbot renews it)"; exit 0
fi

echo "1/3 temporary self-signed certificate"
mkdir -p "$live"
openssl req -x509 -nodes -newkey rsa:2048 -days 2 -subj "/CN=$SIA_HOST" \
  -keyout "$live/privkey.pem" -out "$live/fullchain.pem" 2>/dev/null
echo dummy > "$live/.source"
$C up -d nginx

echo "2/3 Let's Encrypt certificate for $SIA_HOST and $STORE_HOST"
rm -rf "$live" "$LE/archive/$SIA_HOST" "$LE/renewal/$SIA_HOST.conf"
$C run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
  --cert-name "$SIA_HOST" -d "$SIA_HOST" -d "$STORE_HOST" \
  --email "$CERT_EMAIL" --agree-tos --no-eff-email --non-interactive

echo "3/3 reload nginx"
$C exec nginx nginx -t
$C exec nginx nginx -s reload
echo "done: https://$SIA_HOST and https://$STORE_HOST"
