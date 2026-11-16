#!/usr/bin/env bash
# Render config files that need non-secret settings from deploy/env/<env>.env.
#
#   deploy/scripts/render-config.sh <prod|staging>
#
# prometheus/alertmanager.yml.tmpl -> alertmanager.rendered.yml, prometheus/blackbox-targets.yml.tmpl ->
# blackbox-targets.rendered.yml (both git-ignored).
# Alertmanager does not expand ${VARS} itself. Only the listed variables are substituted, and a missing
# one stops the script, so a half-rendered file is never mounted. The SMTP password stays a Docker
# secret (auth_password_file); it is never read here.
set -euo pipefail

ENVIRONMENT=${1:?usage: render-config.sh <prod|staging>}
case "$ENVIRONMENT" in staging|prod) ;; *) echo "bad env: $ENVIRONMENT" >&2; exit 2 ;; esac
DEPLOY_DIR=$(cd "$(dirname "$0")/.." && pwd)
ENV_FILE="$DEPLOY_DIR/env/${ENVIRONMENT}.env"
VARS=(ALERT_EMAIL_TO SMTP_HOST SMTP_USER SIA_HOST STORE_HOST)

# Values already in the environment win over the env file (lets CI or an operator override one).
for name in "${VARS[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    value=$(grep -E "^${name}=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)
    [[ -n "$value" ]] || { echo "render-config: $name is not set (environment or $ENV_FILE)" >&2; exit 1; }
    printf -v "$name" '%s' "$value"
  fi
  # Values go into YAML scalars: refuse anything that could break the structure.
  [[ "${!name}" =~ ^[A-Za-z0-9._@+-]+$ ]] || { echo "render-config: $name has unexpected characters" >&2; exit 1; }
done

render() {  # <template> <output>
  local tmp line
  tmp=$(mktemp "$2.XXXXXX")
  while IFS= read -r line || [[ -n "$line" ]]; do
    for name in "${VARS[@]}"; do line=${line//\$\{$name\}/${!name}}; done
    printf '%s\n' "$line"
  done < "$1" > "$tmp"
  if grep -n '\${[A-Z_]*}' "$tmp" >&2; then rm -f "$tmp"; echo "render-config: unrendered placeholder in $1" >&2; exit 1; fi
  chmod 644 "$tmp"   # read by the alertmanager container user (65534)
  mv "$tmp" "$2"
  echo "rendered $2"
}

render "$DEPLOY_DIR/prometheus/alertmanager.yml.tmpl" "$DEPLOY_DIR/prometheus/alertmanager.rendered.yml"
render "$DEPLOY_DIR/prometheus/blackbox-targets.yml.tmpl" "$DEPLOY_DIR/prometheus/blackbox-targets.rendered.yml"
