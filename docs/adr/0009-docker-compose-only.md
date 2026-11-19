# ADR-0009: Docker Compose only; one project per host

- Status: Accepted (2026-11-06)
- Related: TRD §10, TAD §9.2, INFRASTRUCTURE, ADR-0013

## Context
One developer runs production on one host and two Pis, with no platform team.

## Options
1. **Kubernetes (k3s)**: self-healing and rolling updates; heavy to learn, run and debug, and uses memory the 32 GB budget doesn't have.
2. **Docker Swarm**: multi-host scheduling; a small ecosystem and little benefit on one host.
3. **Docker Compose**: one file per host, already familiar.

## Decision
Option 3. Projects `sia-prod` and `sia-staging` (on demand) on the host, `sia-db-a/b` on the Pis. Every container has `mem_limit` and `cpus`, a read-only root filesystem, dropped capabilities and `no-new-privileges`. Images are pinned by digest and cosign-verified by `deploy/scripts/deploy.sh`, which rolls back to the previous digest if health or smoke checks fail.

## Consequences
- Scaling is `--scale <svc>=n` on the one host; no cross-host scheduling (ADR-0013).
- Rolling updates, health gating and rollback come from our own `deploy.sh`.
- The platform is reproducible from the repo (`provision.sh`), checked by the platform rehearsal in CI.
