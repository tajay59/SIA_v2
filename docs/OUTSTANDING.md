# Outstanding work to finish CIMH Stores v2

As of 2026-11-19. Everything in phases P0–P8 is built; what is left is merging open work, hardware and on-site tests, the migration rehearsals, documents for users, and the cut-over itself. Go-live criteria: TEST_STRATEGY §11. Order of work: top to bottom.

**Who:** **Owner** = only you can do it (access, hardware, decisions, people). **Claude** = can be done in a session here. **Both** = Claude prepares, you run or sign.

## 1. Open pull requests (now)

| # | Item | Who |
|---|---|---|
| 1.1 | Merge [#47](https://github.com/tajay59/SIA_v2/pull/47) cut-over run book + production loaders (auto-merge on, CI running) | Claude (watch) |
| 1.2 | Merge [#48](https://github.com/tajay59/SIA_v2/pull/48) ADRs, then [#49](https://github.com/tajay59/SIA_v2/pull/49) safe M08 re-runs; retarget each to `main` once the PR below it merges | Claude |

## 2. Security and access (blocks go-live; do first)

| # | Item | Who |
|---|---|---|
| 2.1 | Revoke the GitHub token in `git.txt`; rotate the Mongo admin password (exposed in chat) and the credentials in `legacy/sia/.env` | Owner |
| 2.2 | Rotate legacy secrets and `svc_migrate_ro`; deploy the P0 legacy fixes and verify TLS on the legacy server (P0 exit, never tested against a running legacy app) | Owner (Claude can help test) |
| 2.3 | Archive customer files on the legacy server; purge customer files from the old `SIA/` git history (`git filter-repo`) before it is pushed anywhere | Owner |
| 2.4 | ADR-0012 (places in `misc`): accept or ask for the move | Owner |

## 3. Hardware and network (blocks P9)

| # | Item | Who |
|---|---|---|
| 3.1 | VLAN, IPs and DNS from CIMH IT (INFRASTRUCTURE §10 steps 1–3; gate before any deploy) | Owner + CIMH IT |
| 3.2 | Decide the 64 GB RAM upgrade (by DR-2; budget is 29.5–31.5 GB of 32) | Owner |
| 3.3 | Two Raspberry Pi 5 (ARMv8.2-A+; a Pi 3B cannot run MongoDB 8), LUKS, `check-db-host.sh` | Owner |
| 3.4 | Run `deploy/scripts/provision.sh prod` on sia-host; self-hosted GitHub runner (deploy jobs); first production deploy by digest | Both |
| 3.5 | Real restore of a production backup into staging (P1 exit) | Both |

## 4. Finish P7 and P8 exits

| # | Item | Who |
|---|---|---|
| 4.1 | NVDA screen-reader pass on SHOP and SIA (P7 exit; go-live criterion) | Owner |
| 4.2 | Create the Android upload key (`tools/mobile/make-upload-key.sh`) and add the 3 GitHub secrets so CI signs the APK | Owner |
| 4.3 | J-09 on the Galaxy Note 10+ with the **signed release APK**: offline sync, Bluetooth scanner, camera photos | Owner |
| 4.4 | SHOP home hero image and the two sign-in pictures (`packages/web-app/src/assets/auth/`, prompts in its `SOURCE.md`); check the sign-in transition once with motion on, incl. Safari | Owner |
| 4.5 | Staff email lists on staging are empty: an admin fills them in A-19 | Owner |

## 5. Hardening on real hardware (P9)

| # | Item | Who |
|---|---|---|
| 5.1 | k6 performance runs at production size on sia-host (TEST_STRATEGY §6); scale replicas to the 1,000 req/s target | Both |
| 5.2 | Resilience on hardware: Pi down, power cut with manual LUKS unlock, failover/fail-back (TEST_STRATEGY §7) | Both |
| 5.3 | Missing TR-OBS-3 alerts listed in `docs/runbooks/MONITORING.md` | Claude |
| 5.4 | Authenticated ZAP full scan against the final build (go-live: no high) | Claude |
| 5.5 | Requirements Traceability Matrix generated from test tags; every PRD Must has ≥ 1 passing test (go-live criterion) | Claude |
| 5.6 | Triage: 0 open S1/S2, S3s dated | Both |

## 6. Migration rehearsals (P9)

| # | Item | Who |
|---|---|---|
| 6.1 | G4: create read-only `svc_migrate_ro` on 172.16.0.203 | Owner |
| 6.2 | G5: legacy nginx maintenance page (503 + page; `/sia/api/` 503 JSON) | Claude writes, owner applies |
| 6.3 | G6: copy `app/uploads/` and `app/tempquotations/` from the legacy server; load the 66 missing order files into staging with `files_to_v2.py --orders-only` | Owner fetches, Claude loads |
| 6.4 | Admins assign an organisation to the 29 active customers without one (DR report warning = 0) | Owner (admins) |
| 6.5 | DR-2 on staging (first real run of `load_prod.sh` / `load_files_prod.sh`), incl. logins with real legacy passwords and the staff spot-check | Both |
| 6.6 | DR-3 ≤ 7 days before cut-over with a fresh dump and `docs/runbooks/CUTOVER.md` unchanged: ≤ 45 min, zero manual fixes | Both |
| 6.7 | Dry-run reports (#19) for DR-1/2/3 | Claude |

## 7. Acceptance (P9 exit)

| # | Item | Who |
|---|---|---|
| 7.1 | UAT by staff and admins (staff play customers with test accounts) | Owner + staff |
| 7.2 | Product-owner sign-off = go decision (MS7) | Owner |

## 8. Documents still planned

| # | Doc (index #) | Who |
|---|---|---|
| 8.1 | Coding Standards and Contribution Guide (#13): `CONTRIBUTING.md` exists, index not updated | Claude |
| 8.2 | Service/app READMEs (#14), generated API reference (#15): mostly exist or generate from `docs/api/`; check and mark | Claude |
| 8.3 | Test plans (#16), changelog/release notes (#18), load and security test reports (#20; pen test notes in `docs/security/`) | Claude |
| 8.4 | User guides SHOP/SIA/Mobile (#26), Admin guide (#27), Training material (#28): staff training is due T-7 d | Claude drafts, owner reviews |
| 8.5 | Support policy (#29), Privacy policy and Terms (#30; Barbados DPA 2019): needed before go-live | Claude drafts, owner/legal approve |
| 8.6 | Handover guide (#31), Close-out report (#32) | Claude, at the end |

## 9. Cut-over and hypercare (P10)

| # | Item | Who |
|---|---|---|
| 9.1 | T-7 d: staff trained, signed APK on every staff device | Owner |
| 9.2 | T-5 d: announce the window (email + SHOP banner) | Owner |
| 9.3 | Run `docs/runbooks/CUTOVER.md`: freeze, export, convert + check, load, verify, go/no-go, switch, smoke | Both |
| 9.4 | Hypercare 30 days: daily alert review, SHOP feedback link, rollback allowed ≤ 48 h | Both |
| 9.5 | T+1 d: email customers with SUBMITTED paid requests (formal quote follows) | Owner |
| 9.6 | T+30 d: archive the legacy DB + files (restic), decommission Flask, delete the SQLite token store, rotate anything it held; delete old `SIA/`, `SHOP/`, `v2/` copies when you say so | Owner |
