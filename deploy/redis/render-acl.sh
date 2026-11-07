#!/usr/bin/env bash
# Render redis_users.acl from the per-user password secrets (TR-SEC-7, INFRASTRUCTURE §5.3).
# Key patterns follow the key names used in code; a service can only touch its own keys.
#   deploy/redis/render-acl.sh [secrets-dir]
set -euo pipefail
DIR=${1:-$(cd "$(dirname "$0")/.." && pwd)/secrets}
OUT="$DIR/redis_users.acl"

# Commands every service user needs; nothing administrative (no KEYS, FLUSH*, CONFIG, DEBUG, ACL).
BASE="+@read +@write +@string +@set +@hash +@sortedset +@list +@keyspace -@dangerous +eval +evalsha +ping +info"
# Every service checks revocations (TokenVerifier) and keeps its own processed-event ids and locks.
COMMON='%R~revoked:* ~processed:${svc}:* ~lock:${svc}:*'

declare -A KEYS=(
  [identity]='~sess:* ~user_sess:* ~rt:* ~rt_used:* ~revoked:* ~totp_step:* ~svc:*'
  [catalog]='~cat:*'
  [inventory]='~inv:*'
  [order]='~ord:*'
  [document]='~doc:*'
  [notification]='~ntf:*'
  [relay]='~lock:outbox-relay:*'
)

tmp=$(mktemp)
echo "user default off" > "$tmp"
for svc in "${!KEYS[@]}"; do
  pw=$(cat "$DIR/redis_$svc")
  common=${COMMON//\$\{svc\}/$svc}
  echo "user $svc on >$pw resetkeys ${KEYS[$svc]} $common resetchannels $BASE" >> "$tmp"
done
pw=$(cat "$DIR/redis_exporter")
echo "user exporter on >$pw resetkeys resetchannels -@all +ping +info +client|list +config|get +slowlog|get +latency|latest +select +scan +type +strlen +llen +scard +zcard +hlen +xlen" >> "$tmp"
install -m 400 "$tmp" "$OUT"; rm -f "$tmp"
echo "rendered $OUT"
