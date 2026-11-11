# Backup and disaster recovery plan (#23)

For: the person restoring service after a failure. Targets (TRD TR-REC-1): **RPO ≤ 24 h, RTO ≤ 4 h** after total loss of the main host. Background: INFRASTRUCTURE §7, §12.

## What is backed up

| Data | How | Where | Kept |
|---|---|---|---|
| MongoDB (all collections) | `backup.sh` nightly: `mongodump --oplog` from a **secondary** (Pi B), streamed into restic, plus a manifest of per-collection counts | restic repository at the other CIMH site (append-only credentials) | 30 daily + 12 monthly |
| Files `/srv/sia-data` (product images, protected documents) | restic, same run | same | same |
| Configuration | git (`deploy/`); secrets in the CIMH password manager | GitHub + password manager | — |

The rehearsal (`tools/infra/rehearsal/run.sh`, CI on `main`) proves backup → restore → counts on every change to the platform. Restores use `--bypassDocumentValidation` so documents older than a validator change are never dropped.

## Scenarios

### A. One Pi fails
No user impact (the replica set keeps a majority). Alert `ReplicaSetMemberDown`.
1. Replace or re-image the Pi (`bootstrap`, LUKS), start `compose.pi.yml`.
2. It rejoins and runs an initial sync; watch `rs.status()` until SECONDARY.

### B. sia-host down, Pis fine
Services are down; data is safe and current on the Pis (a Pi becomes primary within 30 s).
1. Repair, or rebuild the host from `bootstrap` + `deploy/` (INFRASTRUCTURE §10 steps 2–8).
2. Restore `/srv/sia-data` from restic: `restic restore latest --target / --include /srv/sia-data`.
3. Start mongo1: it rejoins, catches up, and takes primary back (priority 10). Start the rest; nginx with the existing certificates (or `nginx/certs.sh`).
4. Smoke test (`scripts/smoke.sh prod <service>` for each), then announce.

### C. Host and both Pis lost (fire, theft)
1. New hardware; INFRASTRUCTURE §10 steps 1–8 (CIMH IT: VLAN, IPs, DNS).
2. Restore MongoDB into the new mongo1 (`backup` image): `restore.sh latest` with `MONGO_URI` pointing at the new primary → **check every collection count against the manifest** (the script fails on any difference).
3. Restore `/srv/sia-data`; start Pis; they initial-sync from mongo1.
4. Up to 24 h of changes are lost: tell users which window to re-enter (orders since the snapshot time).

### D. Ransomware or data corruption
1. Stop writes: `$C stop` the services (keep Mongo up for inspection).
2. Find the last good snapshot (`restic snapshots`; check the manifest counts and the `auditlog` around the event).
3. Restore into staging first, verify, then into production (scenario C step 2 with that snapshot).
4. The restic repository is append-only for the backup credentials, so the attacker cannot have encrypted it.

### E. Power cut
1. Host and Pis restart by themselves (BIOS "power on after AC loss").
2. **Unlock each Pi's LUKS disk by hand** (console or `ssh` into the unlock environment); until then the host's mongo1 is alone and cannot be primary (no majority): the platform waits.
3. Check `rs.status()`, then containers; alert `HostRebooted` fires and clears.

## Tests (DR-2, DR-3: owner, on the real machines)

| Test | When | Pass |
|---|---|---|
| Restore latest backup into staging | Monthly | counts match the manifest; SHOP shows products; a test request opens |
| Pi stop / host stop (failover) | Quarterly | Pi primary < 30 s; host takes primary back |
| Full rebuild from nothing (DR-3) | Before go-live, then yearly | service back within 4 h; data loss ≤ 24 h |

Record each test (date, time taken, problems) at the bottom of this file.

## Test log

| Date | Test | Result | Notes |
|---|---|---|---|
| 2026-11-10 | DR-1 (migration dry run on a throwaway Mongo) | Pass (34/1 warning) | MIGRATION_PLAN §7 |
| 2026-11-11 | Rehearsal backup → restore (CI) | Pass | restore bypasses validators |
