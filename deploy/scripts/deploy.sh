#!/usr/bin/env bash
# Deploy one service image to staging or production on sia-host.
# Run ONLY by the self-hosted GitHub runner (user `deploy`), which may execute deploy/scripts/* only.
#
#   deploy/scripts/deploy.sh <staging|prod> <service> <sha256:digest>
#
# Steps: verify cosign signature -> pull -> up -d -> wait for /health/ready -> smoke -> or roll back.
set -euo pipefail

ENVIRONMENT=${1:?env}; SERVICE=${2:?service}; DIGEST=${3:?digest}
REGISTRY=${REGISTRY:-ghcr.io/tajay59}
# Only images signed by this repository's CI on main are deployed (TR-SEC-9).
COSIGN_IDENTITY=${COSIGN_IDENTITY:-^https://github.com/tajay59/SIA_v2/.github/workflows/ci.yml@refs/heads/main$}
DEPLOY_DIR=$(cd "$(dirname "$0")/.." && pwd)
COMPOSE_FILE="$DEPLOY_DIR/compose.${ENVIRONMENT}.yml"
STATE_DIR=/srv/sia-deploy/${ENVIRONMENT}
VAR=$(echo "${SERVICE}" | tr 'a-z-' 'A-Z_')_DIGEST

case "$ENVIRONMENT" in staging|prod) ;; *) echo "bad env: $ENVIRONMENT" >&2; exit 2 ;; esac
[[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "bad digest" >&2; exit 2; }
[[ "$SERVICE" =~ ^[a-z-]+$ ]] || { echo "bad service" >&2; exit 2; }
mkdir -p "$STATE_DIR"

IMAGE="${REGISTRY}/${SERVICE}@${DIGEST}"
echo "Verifying signature of $IMAGE"
cosign verify "$IMAGE" \
  --certificate-identity-regexp "$COSIGN_IDENTITY" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com >/dev/null

PREVIOUS=$(cat "$STATE_DIR/$SERVICE.digest" 2>/dev/null || true)

up() {
  export "$VAR=$1"
  docker compose -f "$COMPOSE_FILE" pull "$SERVICE"
  docker compose -f "$COMPOSE_FILE" up -d --no-deps --wait --wait-timeout 120 "$SERVICE"
}

if up "$DIGEST" && "$DEPLOY_DIR/scripts/smoke.sh" "$ENVIRONMENT" "$SERVICE"; then
  echo "$DIGEST" > "$STATE_DIR/$SERVICE.digest"
  echo "Deployed $SERVICE $DIGEST to $ENVIRONMENT"
else
  echo "Deploy failed; rolling back to ${PREVIOUS:-nothing}" >&2
  if [[ -n "$PREVIOUS" ]]; then up "$PREVIOUS"; fi
  exit 1
fi
