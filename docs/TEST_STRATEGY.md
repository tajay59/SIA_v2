# Test Strategy: CIMH Stores Platform v2

| | |
|---|---|
| **Document status** | DRAFT |
| **Document owner** | T. Edwards |
| **Related documents** | [PRD](PRD.md) (requirement ids) · [TRD](TRD.md) (targets) · [API](api/README.md) · [APD](APD.md) (journeys) · [SECURITY §11](SECURITY.md) · [MIGRATION_PLAN §6–7](MIGRATION_PLAN.md) · [INFRASTRUCTURE §9](INFRASTRUCTURE.md) |
| **Last updated** | 2026-11-06 |

---

## 1. Purpose

Agrees **how "done" and "ready to launch" are proved**: which kinds of test exist, which tools, how much coverage, where tests run, what data they use, what blocks a merge or a release, and how every PRD requirement is traced to a test.

## 2. Quality goals (what the tests must prove)

| Goal | Source | Proved by |
|---|---|---|
| Every PRD "Must" works as specified | PRD §5 | Unit + integration + E2E, traced in the RTM |
| Nobody sees or changes data they shouldn't | SECURITY T-12…T-16 | Generated authorisation/IDOR suite (100 % of endpoints) |
| Status flows can't be broken (illegal transitions, double acceptance, oversold stock) | TAD §6.3, §7 | Domain unit tests (state machines), concurrency integration tests |
| API matches the spec | API specs | Contract tests (Schemathesis + event schema checks) |
| p95 < 300 ms reads / < 500 ms writes at 1,000 req/s; error rate < 0.1 % | TRD TR-PERF | k6 load tests |
| Survives loss of one MongoDB member or Kafka broker | TRD TR-AVAIL-2 | Resilience tests |
| WCAG 2.1 AA | TRD TR-ACC-1, Design Brief §11 | axe in CI + manual screen-reader pass |
| Migration loses nothing | MIGRATION_PLAN §6 | Migration verification suite + dry runs |
| No high/critical security findings | SECURITY §11 | SAST/DAST/dependency scans + **penetration test by Claude** (OWASP ASVS L2) |

## 3. Test levels (pyramid)

![Test pipeline](manual/images/30-test-pipeline.svg)

| Level | What | Tools | Where | Target |
|---|---|---|---|---|
| **Unit** | Domain rules (status machines, pricing, CIMH option, exchange rate, Pro Bono limits, split cart), validators, mappers | pytest, Vitest, JUnit (Android) | Every PR, < 2 min | ≥ 90 % lines on `domain/`; ≥ 80 % service logic overall (TR-CI-6) |
| **Integration** | Repositories against real MongoDB (replica set, transactions), Kafka producers/consumers, outbox relay, Redis revocation, idempotency | pytest + **testcontainers** (MongoDB RS, Kafka, Redis) | Every PR | Every repository method and consumer |
| **Contract (API)** | Each service conforms to its OpenAPI spec; responses never include undeclared fields | **Schemathesis** (property-based) against a running service | Every PR | All endpoints, all documented status codes |
| **Contract (events)** | Produced events validate against `events.asyncapi.yaml`; consumers accept every documented version | JSON-Schema validation in producer tests; Apicurio compatibility check in CI | Every PR | Every event type |
| **Authorisation / IDOR** | For every endpoint × role × ownership case: allowed → 2xx, forbidden → 403, not visible → 404 | Generated pytest suite from the API role table (§5) | Every PR | **100 % of endpoints** |
| **Component (web)** | `packages/web-ui` components (status chip, quote comparison, agreement stepper, money input) | Vitest + Vue Test Utils; Playwright component tests + screenshot comparison | Every PR | Every shared component, light + dark |
| **End-to-end** | User journeys J-01–J-11 through real UIs and services | **Playwright** (Chromium, Firefox, WebKit; mobile viewport) | Every merge to `main` on staging; nightly full | All journeys + main alternatives |
| **Mobile** | Scan flows, offline queue, Keystore auth | Compose UI tests, Robolectric, instrumented tests on an **Android 12 emulator** (minimum version) + the warehouse device, a **Samsung Galaxy Note 10+ (SM-N975U1)** | Every PR (unit/UI), nightly (instrumented) | M-01–M-11 |
| **Performance** | Load, stress, soak | **k6** | Before each release on staging (sized as prod) | TRD TR-PERF-1…3 |
| **Resilience** | Kill a Pi / broker / service replica; primary step-down; Redis restart; disk full | Scripted chaos (`deploy/tests/chaos/*.sh`) | Before go-live, then quarterly | TR-AVAIL-2 |
| **Security** | SAST, dependency, image, secrets, DAST, penetration test (Claude) | Semgrep, Bandit, pip-audit, npm audit, Trivy, gitleaks, OWASP ZAP, internal ASVS review | PR / nightly / release / yearly | SECURITY §11 |
| **Accessibility** | Automated rules + manual | axe-core (Playwright), NVDA (Windows), TalkBack (Android) | Every E2E run; manual before release | WCAG 2.1 AA, 0 serious/critical axe issues |
| **Migration** | Mapping, verification, timing | `migrate --dry-run/--verify` | DR-1, DR-2, DR-3 | MIGRATION_PLAN §6 all green |
| **UAT** | Staff and admins run real tasks; **customer journeys are played by CIMH staff using test customer accounts** (no external organisations) | Scripted scenarios on staging | Before go-live | Sign-off by the product owner |

## 4. What gets tested where (critical areas)

| Area | Key cases |
|---|---|
| **Registration and approval** | Code expiry and attempts; `@cimh.edu.bb` auto-activate and **cannot request**; approval requires an organisation; bulk decision partial failures (207); login blocked per status with the right code |
| **Tokens** | Refresh rotation; **reuse detection revokes the session family**; logout revokes; suspension revokes immediately; JWKS key rotation overlap; expired/forged/`alg=none` tokens rejected |
| **Cart and submission** | Pro Bono limit; mixed cart → **two requests**; currency required with paid lines; inactive product rejected; idempotent submit (double click → one request) |
| **Quote → agreement → acceptance** | CIMH option only when **full** quantity available; USD requires exchange rate; quote versioning; accept only latest version; `AWAITING_AGREEMENT` change-choices regenerates agreement; accept requires `signed_agreement` of this request; staff reject signature → back to AWAITING; expiry job cancels at 30 days and reminder at 27 days |
| **Reservation and stock** | **Concurrent reservations for the same last units** (two requests at once → one wins, other `reservation_failed`); release on cancel and on signature rejection; picking only reserved units; supplier lines not pickable; stock counts match history |
| **Status machine** | Every allowed transition succeeds; **every disallowed transition returns 409** (generated from the transition table); conditional update prevents lost updates under parallel requests |
| **Events** | Outbox: crash after DB write but before publish → event still published; duplicate delivery → applied once; poison message → retry → DLQ + alert |
| **Files** | Magic-byte check (renamed `.exe` → 415); ClamAV EICAR test file → quarantined; size limit; download permission matrix; `X-Accel-Redirect` path never user-controlled |
| **Notifications** | Each event produces exactly one email with the right deep link (APD §7); templates escape injected HTML |
| **Search and paging** | Text search relevance basics; cursor paging stable under inserts; `limit` caps |
| **Mobile offline** | Scans queued offline sync once; server rejection appears in M-11; idempotency key reuse |

## 5. Authorisation test generation

A single YAML table (`tests/authz/matrix.yaml`), derived from the API README §3, lists every endpoint with the allowed roles and the ownership rule (`self`, `same_org`, `requester`, `staff`, `admin`, `public`). A generator creates, per endpoint:

1. anonymous → 401 (or 200 if public);
2. each role not allowed → 403;
3. allowed role on **another user's / organisation's** resource → **404** (hidden);
4. allowed role on own resource → 2xx;
5. `@cimh.edu.bb` user on cart/request endpoints → 403 `CIMH_CANNOT_REQUEST`.

CI fails if an endpoint exists in a running service but **not** in the matrix (no untested endpoint can ship).

## 6. Performance tests (k6)

| Scenario | Load | Pass criteria |
|---|---|---|
| **Browse mix** (60 % catalogue/search, 20 % product detail, 10 % my requests, 10 % login/refresh) | Ramp to **1,000 req/s**, hold 30 min | p95 < 300 ms, p99 < 1 s, errors < 0.1 % (TR-PERF-1/3) |
| **Write mix** (cart updates, submissions, staff actions, scans) | 100 req/s alongside browse | p95 < 500 ms (TR-PERF-2); no 409 storms except intended conflicts |
| **Stress** | Increase until failure | Graceful degradation (429/503, no data corruption); find the knee |
| **Soak** | 300 req/s for 8 h | No memory growth beyond limits; no consumer lag build-up |
| **Burst** | 20,000 concurrent sessions logging in over 10 min | Login p95 < 1 s (Argon2 cost tuned accordingly) |

Test data: 2 M products, 30 M units, 1.5 M orders generated synthetically on staging (sized-as-prod run done with staging stack alone, TRD §6.3). Memory and CPU per container recorded and compared to INFRASTRUCTURE §4.1. **Results feed the 64 GB upgrade decision** (INFRASTRUCTURE Q4).

### 6.1 Phase checks (before P9)

Each service phase ends with a smaller check on the dev stack, with **one** container at its production limits (half of production for catalog-svc, which runs 2 replicas). Tools live in `tools/perf/`:

| Tool | Does |
|---|---|
| `seed_catalog.py` | Bulk-seeds synthetic products (`seedTag: "perf"`, removed with `--cleanup`) |
| `querylog.py` + `explain_<service>.py` | Records the queries the real service methods send and runs `explain` on each: FAIL on a collection scan, WARN on an in-memory sort or > 100 documents examined per result (a `$text` relevance sort is allowed). The same cases run in CI on 20k products (`tests/integration/test_query_plans.py`), which enforces **TR-DATA-5** |
| `<service>.k6.js` + `run_<service>.sh` | k6 in Docker: `MODE=steady` (gate) or `MODE=knee` (ramp, no gate); results in `tools/perf/results/` (git-ignored) |

| Phase | Data | Load | Result |
|---|---|---|---|
| **P3 catalogue** (2026-11-07) | 200k products | 55 req/s for 3 min: 35 % lists (+ next page), 25 % detail, 25 % search, 15 % staff | **Pass.** p95 43 ms, p99 71 ms, 0 errors in 9,927 requests; search p95 68 ms; 132 of 256 MB. 55 of 55 queries index-backed (fixed on the way: "show inactive" scanned all 200k products; type filters relied on MET being common) |
| **P4 inventory** (2026-11-07) | 200k units, 2k products, 400k history rows (`explain_inventory.py`) | Explain only (P4's gate is the concurrency test, below) | **Pass.** 133 queries, all index-backed incl. the partial indexes (fixed on the way: assigned count filtered every unit of a product; unit lists looked up product names one by one) |

Concurrency (P4 exit): `tests/integration/test_inventory.py` races two reservations for the last units (one wins, the loser holds nothing), two requests taking the same two products in opposite order (only possible to get right with the transaction; the test fails with transactions switched off), and two devices scanning the same unit.

**Findings for P9:**
- One catalog-svc container (0.5 CPU, 2 workers) is **CPU-bound in Python**: p95 stays < 80 ms up to ~145 req/s, then requests queue (no errors, but p95 reaches seconds by ~250 req/s). The 1,000 req/s browse mix (~850 req/s on the catalogue) therefore needs about **6 replicas at 0.5 CPU or more CPU per replica**, not today's 2 × 0.5 (INFRASTRUCTURE §4.1). This is CPU, not memory.
- `$text` ranking sorts all matches in memory: ~30 ms for ~10k matches at 200k products. At 2M products a broad word ("sensor") matches ~100k, so search is the first read to check in P9.

## 7. Resilience tests

| Test | Expected | Where it runs (P9) |
|---|---|---|
| Stop Pi A | No user impact; alert "member down" | **Rehearsal** (`tools/infra/rehearsal/run.sh` §9): member health 0 in `mongodb-exporter`; alert rule in promtool tests. Real Pi: owner |
| Stop sia-host mongo1 | Pi becomes primary within 30 s; writes resume; host rejoins and takes primary back | **Rehearsal** §7 |
| Stop one Kafka broker | No message loss; producers continue (`min.insync.replicas=2`) | **Rehearsal** §9: relay publishes, event read back |
| Kill a service replica mid-request | nginx retries idempotent GETs; client retries POST with the same Idempotency-Key → one effect | Idempotency replay: unit/integration tests (`IdempotencyStore`); nginx retry: on the host (owner) |
| Restart Redis | Revocations survive (AOF); rate limits reset (acceptable) | **Rehearsal** §9 |
| Outbox relay down 10 min | Events queue on documents; published on restart; alert "outbox backlog" fired | **Rehearsal** §9 (backlog metric, drain, event read back); alert `OutboxBacklog` in `deploy/prometheus/tests/alerts.test.yml` |
| Disk 90 % | Alert at 80 %; services keep running; Kafka retention trims | Host (owner) |
| Power cut simulation | Pis need manual LUKS unlock; runbook steps work; RTO measured | Host + Pis (owner) |

Alert rules are checked in CI (`promtool check config` + `test rules`). Found in P9: the production Prometheus config did not parse (unquoted `${ENV}` in a flow mapping) and the MongoDB/Kafka/Redis exporters it scraped did not exist, so three alerts could never fire; both fixed.

## 8. Test environments and data

| Environment | Data | Notes |
|---|---|---|
| Local | Seed script (fake data, faker), fixed ids for tests | `compose.dev.yml`; Mailpit catches email |
| CI | testcontainers per test module; factories | No shared state between jobs |
| Staging | **Anonymised copy** of production (names, emails, phones, addresses masked; files replaced by placeholders) + synthetic volume for load tests | Started on demand; E2E and load runs; LAN-only access |
| Production | — | Smoke tests only (read-only + a test request created and cancelled by a test account) |

Rules: **no real personal data outside production**; test accounts are clearly named (`test-user-*@example.cimh`) and excluded from emails and reports.

## 9. CI gates

| Stage | Runs | Blocks merge / deploy if |
|---|---|---|
| PR | lint, type-check, unit, integration (testcontainers: Mongo RS, Redis, Kafka), contract (Schemathesis against `docs/api`), authz, component, SAST, dependency/secret scans, shellcheck + actionlint + compose render, SHOP/SIA build, **Playwright journeys J-01, J-08, J-10, J-11** and the personal-data journey (J-10 runs the real image pipeline: relay, Kafka, media-worker) (production builds against the dev stack), **SIA Mobile** JVM unit tests + Android lint (warnings fail) + debug/release build, a11y on components | Any failure; coverage below target; high/critical vulnerability; untested endpoint |
| Merge to `main` → staging | Image build + Trivy, cosign sign, platform rehearsal (`tools/infra/rehearsal`), deploy staging, E2E smoke (J-01, J-02, J-03, J-09) | Any failure → staging rollback |
| Nightly | Full E2E (all journeys, 3 browsers), instrumented Android, ZAP baseline, full dependency scan | Failure opens an issue (severity S2 by default) |
| Release candidate | Full regression, k6 performance, resilience subset, manual a11y, UAT sign-off (go-live) | Any S1/S2 open; performance targets missed |
| Production deploy | Health checks + smoke tests | Automatic rollback to previous SHA on failure |

## 10. Defect severity

| Severity | Definition | Examples | Release |
|---|---|---|---|
| **S1 Critical** | Security breach, data loss/corruption, platform down, money/commitment wrong | IDOR leak, oversold stock, wrong quote total, failed migration check | Blocks; fix immediately |
| **S2 High** | Core journey broken, no workaround | Can't accept a quote, can't scan in mobile | Blocks |
| **S3 Medium** | Feature impaired, workaround exists | Filter wrong, email link opens wrong tab | Allowed with a fix date |
| **S4 Low** | Cosmetic | Spacing, typo | Allowed |

## 11. Entry and exit criteria

**Release candidate entry:** all PR gates green; feature complete for the release's PRD scope; staging deployed; test data loaded.

**Go-live exit:**
- 0 open S1/S2; S3s have dates.
- Every PRD **Must** has ≥ 1 passing automated test (RTM 100 %).
- Performance and resilience targets met (or 64 GB decision taken).
- Authorisation suite 100 % of endpoints; DAST (authenticated ZAP full scan) no high; **Claude-run penetration test** (staging, ASVS L2) findings high+ fixed.
- 0 serious/critical axe issues; manual screen-reader pass done.
- Migration DR-3 green within 45 min.
- UAT signed by the product owner.

## 12. Traceability

The **Requirements Traceability Matrix** (Documentation Index #17, `RTM.md`) is generated from test tags: each test is tagged with the requirement ids it covers (`@req("O6")`, `@req("TR-AUTH-1")`, `@threat("T-12")`, `@journey("J-03")`). A CI job builds the matrix (requirement → tests → last result) and fails the release gate if a Must has no passing test.

## 13. Roles

| Role | Responsibility |
|---|---|
| Developers | Unit, integration, contract, component tests with every change; tags for traceability |
| QA / tech lead | Authz matrix, E2E suites, performance and resilience runs, release sign-off on quality |
| Staff (stores) | UAT scenarios for SIA and Mobile |
| Admins | UAT for approvals, organisations, settings |
| CIMH staff as "customers" | UAT for SHOP journeys, using test customer accounts in fictitious test organisations on staging (not their own `@cimh.edu.bb` accounts, which can't request) |
| **Claude (Claude Code)** + tech lead | **Penetration test** before go-live and yearly: Claude runs it against **staging only**, under a written scope and authorisation from the owner (targets, accounts, time window, no production, no DoS). Covers the OWASP ASVS Level 2 checklist, authenticated ZAP full scan, manual probes of every SECURITY T-xx threat (IDOR, token reuse, agreement forgery, upload abuse, injection). Findings are filed as S1–S4 issues; the tech lead reviews and signs off |

## 14. Questions

| # | Question | Outcome |
|---|---|---|
| 1 | Which member-state organisations join UAT? | **Resolved:** none. CIMH staff test the customer journeys with test accounts. Risk: real-customer usability issues may only appear after launch, so collect feedback in the first month (a SHOP feedback link). |
| 2 | Which warehouse Android device? | **Resolved:** **Samsung Galaxy Note 10+ (SM-N975U1)**. It's the physical test device, alongside the Android 12 emulator (minimum supported). |
| 3 | External penetration test? | **Resolved:** no budget. **Claude performs the penetration test** on staging (scope and authorisation in writing) plus ASVS L2 + authenticated ZAP. Residual risk (not independent) in SECURITY R7. |
