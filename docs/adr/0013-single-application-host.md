# ADR-0013: Single application host; scaling out beyond one host deferred

- Status: Accepted (2026-11-06)
- Related: TRD §6, TAD §9.3, TAD R1–R2, ADR-0004, ADR-0009

## Context
The hardware is one host and two Pis. The Pis are too small to run the services.

## Options
1. **All services, Kafka, Redis and the Mongo primary on the host**; the Pis only as Mongo secondaries.
2. **Spread services across machines now**: needs more hardware, an orchestrator and shared storage (ADR-0008, ADR-0009).

## Decision
Option 1. Scaling means a bigger host or more replicas on it. Going multi-host needs a new ADR.

## Consequences
- The host is a single point of failure for the service (RTO 4 h, DISASTER_RECOVERY), not for the data (ADR-0004).
- Memory is tight (29.5–31.5 GB with ClamAV); every container has `mem_limit`. A 64 GB upgrade is strongly recommended (decide by DR-2).
- P9 measured one catalog container at ~145 req/s (CPU-bound), so about 6 replicas reach the 1,000 req/s target.
