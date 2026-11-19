# ADR-0004: Replica set with the primary on the main host and secondaries on two Raspberry Pi 5

- Status: Accepted (2026-11-06)
- Related: TRD §6, INFRASTRUCTURE §5.1, DISASTER_RECOVERY run book, ADR-0013

## Context
Hardware is one main host (16 cores, 32 GB, 2 GPUs) and two Raspberry Pi 5. Transactions (needed for reservations) require a replica set, and losing the host must not lose data.

## Options
1. **Standalone mongod on the host + backups**: no transactions; data loss up to the last backup.
2. **Three members on the host**: transactions, but one machine still takes every copy down.
3. **Primary on the host (priority 10), secondaries on the two Pis**: three machines, automatic failover, data on separate hardware.

## Decision
Option 3. All members run the same `mongo:8.0.30` image; the host takes the primary role back automatically when it returns. The Pis must be ARMv8.2-A or newer (`deploy/scripts/check-db-host.sh`; MongoDB 8 does not run on a Pi 3B).

## Consequences
- Writes use majority write concern; the Pis' storage speed adds some write latency.
- If the host is down the Pis keep the data and can elect a primary, but the services also run on the host, so service stops until it returns (TAD R1, R3).
- Backups run from a secondary (`mongodump --oplog` into restic, off-site).
- Host kernels must avoid 6.19 to 7.0.13 (Mongo 8.0.21–29 refused to start there; pinned to 8.0.30).
