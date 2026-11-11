#!/usr/bin/env bash
# Can this machine run a MongoDB 8.0 replica-set member? Run on each Pi (and sia-host) before compose up.
#
#   bash deploy/scripts/check-db-host.sh            # exit 0 = OK, 1 = refuse (reasons printed)
#
# Checks (INFRASTRUCTURE §2, §4.4):
#   - 64-bit (aarch64 or x86_64); MongoDB has no 32-bit builds
#   - ARM: ARMv8.2-A or later. MongoDB 5.0+ ARM builds need it; a Pi 3/4 (Cortex-A53/A72, ARMv8.0) stops at
#     once with "Illegal instruction". Detected by the LSE atomics + ARMv8.2 FP16/DC CVAP flags. A Pi 5 passes.
#   - memory: >= 4 GB (the Pis get --wiredTigerCacheSizeGB 3); < 8 GB is a warning
#   - kernel: mongo 8.0.21-8.0.29 refuse kernels 6.19+; 8.0.30 is pinned, so 6.19 - 7.0.13 are refused here too
#     (CLAUDE.md, 2026-11-07), to keep a downgrade from becoming an outage.
#   - the replica set needs the SAME MongoDB version everywhere (compose files pin mongo:8.0.30)
set -uo pipefail
fail=0
bad() { echo "REFUSE  $*"; fail=1; }
ok() { echo "ok      $*"; }
warn() { echo "warn    $*"; }

arch=$(uname -m)
case "$arch" in
  x86_64) ok "architecture $arch" ;;
  aarch64|arm64)
    ok "architecture $arch"
    flags=$(grep -m1 -i '^Features' /proc/cpuinfo 2>/dev/null | cut -d: -f2)
    missing=""
    for f in atomics asimdhp dcpop; do grep -qw "$f" <<< "$flags" || missing="$missing $f"; done
    if [[ -n "$missing" ]]; then
      model=$( { tr -d '\0' < /proc/device-tree/model; } 2>/dev/null || echo "unknown board")
      bad "CPU is older than ARMv8.2-A (missing:$missing; $model). MongoDB 5+ will not start (Illegal instruction). Use a Raspberry Pi 5 or newer."
    else
      ok "CPU supports ARMv8.2-A (atomics, asimdhp, dcpop)"
    fi ;;
  *) bad "architecture $arch: MongoDB 8 needs 64-bit aarch64 or x86_64 (32-bit OS? install the 64-bit image)" ;;
esac

mem_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
mem_gb=$(( mem_kb / 1024 / 1024 ))
if (( mem_kb < 3800000 )); then bad "memory ${mem_gb} GB: at least 4 GB needed (cache 3 GB + mongod); swap is not a substitute"
elif (( mem_kb < 7600000 )); then warn "memory ${mem_gb} GB: works, 8 GB recommended"
else ok "memory ${mem_gb} GB"; fi

kernel=$(uname -r)
IFS=. read -r kmaj kmin kpatch _ <<< "${kernel%%-*}"
kpatch=${kpatch:-0}
if (( kmaj == 6 && kmin >= 19 )) || (( kmaj == 7 && kmin == 0 && kpatch < 14 )); then
  bad "kernel $kernel: MongoDB 8.0 refuses 6.19 - 7.0.13; use <= 6.18 or >= 7.0.14"
else
  ok "kernel $kernel"
fi

if command -v docker >/dev/null 2>&1; then ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo present)"
else bad "docker is not installed"; fi

(( fail == 0 )) && echo "this machine can run a MongoDB 8.0 replica-set member" || echo "do NOT start compose.pi.yml here"
exit "$fail"
