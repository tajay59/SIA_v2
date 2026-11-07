# Technical Requirements Document (TRD): CIMH Stores Platform v2

| | |
|---|---|
| **Document status** | DRAFT |
| **Document owner** | T. Edwards |
| **Related documents** | [PRD](PRD.md) · TAD (planned) · BSD (planned) · API Spec (planned) · [Documentation Index](DOCUMENTATION_INDEX.md) |
| **Last updated** | 2026-11-06 |

---

## 1. Purpose and scope

This document defines the **tools, techniques and infrastructure** used to build the CIMH Stores Platform v2 (SHOP, SIA web, SIA Mobile and the backend microservices), and the **technical requirements** they must meet. It turns the product requirements in the [PRD](PRD.md) into technical, measurable terms.

How the parts connect is covered in the Technical Architecture Document (TAD). Field-level data definitions are in the Background Schema Document (BSD).

**Requirement IDs:** `TR-<area>-<n>`. Priority uses the same scale as the PRD: **Must / Should / Could**.

## 2. Load assumptions

These figures are used to size the system and set the targets in section 5. Re-check them after launch.

| Item | Assumption |
|---|---|
| Registered users | up to **1,000,000** |
| Peak concurrent users | 2% of registered = **20,000** |
| Peak API rate | **1,000 requests/s** (mostly catalogue reads and search) |
| Order requests | up to 5,000/day (peak 1 per second) |
| Catalogue size | 83 products today (reference DB), planned for up to 2M |
| Storage units | 697 today, planned for up to 30M |
| Orders | 39 today, planned for +1.5M/year at full scale |
| Files | ~3 PDFs per request at ~300 KB each, about 1.5 TB/year at full scale |

## 3. Technology stack

**Every component uses its latest stable release at project start**, except Android (minimum **Android 11**, see 3.3). Exact versions are then pinned in lockfiles and image tags (never the floating `latest` tag) and reviewed every quarter.

### 3.1 Backend services
| Component | Choice | Notes |
|---|---|---|
| Language | **Python** (latest stable) | Type hints required; checked with mypy (strict mode) |
| Web framework | **FastAPI** + **Pydantic v2** | One FastAPI app per service |
| App server | **Uvicorn** workers (inside Gunicorn as process manager) | |
| MongoDB driver / ODM | **PyMongo Async API** + **Beanie** | Motor is not used (being phased out) |
| Kafka client | **aiokafka** | Idempotent producer, `acks=all` |
| Redis client | **redis-py** (asyncio) | |
| Background jobs inside a service | Kafka consumers + **APScheduler** for timed jobs (quote expiry, reminders) | One scheduler leader per service, chosen via a Redis lock |
| PDF generation | **ReportLab** (carried over) | |
| QR / barcode | **segno** (QR), **python-barcode** | Replaces PyQRCode |
| Image processing | **Pillow**; **rembg** + **onnxruntime-gpu** (CUDA) on the host's GPUs (media-worker only) | ML libraries are kept out of the API images |
| Password hashing | **argon2-cffi** (Argon2id) | Existing Werkzeug hashes are upgraded to Argon2id at each user's next login |
| JWT | **PyJWT** | Signed with EdDSA (Ed25519) or RS256 so services can verify tokens without the private key |
| Email | **aiosmtplib** + **Jinja2** templates | |
| Shipping | No carrier APIs. Staff/admin enter the carrier (FedEx, DHL, Hand delivered) and tracking number manually | The existing FedEx API code is removed |
| Testing | **pytest**, pytest-asyncio, **testcontainers** (MongoDB, Kafka, Redis), **Schemathesis** (API contract tests) | |
| Lint / format | **Ruff**, **mypy** | |

### 3.2 Web frontends (SHOP and SIA)
| Component | Choice |
|---|---|
| Language | **TypeScript** (latest stable, `strict: true`) |
| Framework | **Vue 3** (latest stable; Composition API, `<script setup lang="ts">`) |
| Build | **Vite** (latest), Node.js (latest LTS) |
| UI | **Vuetify 4** (one shared theme package) |
| State / routing | **Pinia**; **Vue Router with file-based routing**: routes are generated from the `src/pages/` folder structure, with typed route names and params |
| API client | Generated from OpenAPI with **openapi-typescript** + **openapi-fetch** |
| Forms / validation | **Zod 4** schemas (shared between forms and API response checks) + vee-validate |
| Testing | **Vitest** (unit), **Playwright** (end-to-end), **axe-core** (accessibility) |
| Lint / format | **ESLint** (typescript-eslint, eslint-plugin-vue), **Prettier** |

Both apps live in one repository (pnpm workspace) with shared packages for the API client, theme and UI components. The legacy `X-User: internal` header is dropped; permissions come from the user's role in the token.

### 3.3 Mobile (SIA Mobile, Android)
| Component | Choice |
|---|---|
| Language / UI | **Kotlin** (latest), **Jetpack Compose**, Material 3 (existing codebase) |
| Networking | Retrofit + OkHttp, API types generated from OpenAPI |
| Offline | Room + WorkManager (existing): scans are queued while offline and sent once the connection returns |
| Scanning | CameraX + ML Kit Barcode Scanning |
| Token storage | Android Keystore-backed encrypted storage |
| Minimum Android | **Android 11 (API 30)**; target SDK = latest |

### 3.4 Data, messaging and infrastructure
| Component | Choice | Notes |
|---|---|---|
| Database | **MongoDB** Community (latest stable), **3-member replica set** | Primary on the main host; secondaries on 2 × Raspberry Pi 5 |
| Messaging | **Apache Kafka** (latest) in KRaft mode | 3 brokers on the main host (see section 6.2) |
| Schema registry | **Apicurio Registry** | Checks that event schemas stay compatible with older consumers |
| Cache / sessions / rate limits | **Redis** (latest stable) | Saved to disk (AOF) |
| Reverse proxy / edge | **nginx** (latest stable) | TLS, routing, rate limiting, static files, `X-Accel-Redirect` downloads |
| TLS certificates | **certbot** (Let's Encrypt) | |
| Containers | **Docker Engine** + **Docker Compose** (latest) | One Compose project per host |
| Metrics | **Prometheus** (built-in web UI for queries and graphs) + node-exporter, mongodb-exporter, kafka-exporter, redis-exporter | No Grafana (removed by decision) |
| Alerts | **Prometheus Alertmanager**, sending email through the CIMH mail server | |
| Logs | Structured JSON to stdout, collected by Docker's `local` log driver with rotation (e.g. 10 × 50 MB per container). Viewed with `docker compose logs`, filtered with `jq` | No Loki (no UI without Grafana) |
| Errors | **No separate error tracker.** Unhandled exceptions are logged with stack traces and counted in a Prometheus metric `app_exceptions_total{service, endpoint, type}`, so alerts can fire per error type | Sentry removed by decision |
| Tracing | None at launch. Every log line carries a `traceId` (correlation ID) passed through HTTP and Kafka, so one request can be followed across services by searching the logs | Distributed tracing is a Could |
| Backups | **mongodump** (or Percona Backup for MongoDB) + **restic** to another CIMH site | |
| CI/CD | **GitHub Actions** + GitHub Container Registry | Build/test on GitHub-hosted runners; deploys by a **self-hosted runner** on sia-host (outbound-only) |

## 4. Functional technical requirements

### 4.1 Services and APIs
| ID | Requirement | Priority |
|---|---|---|
| TR-API-1 | Each service exposes a versioned REST API under its own base path (`/api/identity/v1`, `/api/catalog/v1`, `/api/inventory/v1`, `/api/orders/v1`, `/api/documents/v1`). | Must |
| TR-API-2 | Each service publishes its **OpenAPI 3.1** spec. CI fails if the spec changes in a way that breaks existing clients without a version bump. | Must |
| TR-API-3 | All request bodies and parameters are validated by Pydantic models. Unknown fields are rejected. No user input is ever evaluated as code. | Must |
| TR-API-4 | Errors use a standard JSON error body (RFC 9457) with a `traceId` (the request's correlation ID). | Must |
| TR-API-5 | Lists use **cursor paging** (`limit` ≤ 100, `cursor`). Offset/`skip` paging is not allowed on large collections. | Must |
| TR-API-6 | Requests that change state accept an `Idempotency-Key` header, so a retried request is processed only once. Keys are kept 24 h in Redis. | Should |
| TR-API-7 | Every service provides `/health/live` and `/health/ready` (ready means its MongoDB, Kafka and Redis connections are working). | Must |
| TR-API-8 | Calls between services go through internal HTTP with a service token, never through the public nginx. | Must |

### 4.2 Authentication and authorisation
| ID | Requirement | Priority |
|---|---|---|
| TR-AUTH-1 | identity-svc issues **access tokens (15 min)** and **refresh tokens (7 days, a new one issued on every use)**. If an already-used refresh token is presented again, all of that user's sessions are revoked. | Must |
| TR-AUTH-2 | Web: tokens are in `HttpOnly; Secure; SameSite=Lax` cookies, with double-submit CSRF protection on requests that change state. Mobile: `Authorization: Bearer` header. | Must |
| TR-AUTH-3 | Services verify tokens locally with identity-svc's public keys, published as a JWKS (JSON Web Key Set). Revoked token IDs are checked in Redis. | Must |
| TR-AUTH-4 | Tokens are issued only to accounts with status `ACTIVE`. `staff`/`admin` are required for SIA and Mobile; `@cimh.edu.bb` accounts can never submit requests. | Must |
| TR-AUTH-5 | Every endpoint declares its required role. Every resource access is checked against the owner or the user's organisation. Automated tests cover requests made with another user's IDs. | Must |
| TR-AUTH-6 | Login is rate limited per IP and per account. After 5 failed attempts, the account is locked for 15 min, with each further lockout lasting longer. | Must |
| TR-AUTH-7 | Passwords: at least 12 characters, checked against known-breached passwords (Have I Been Pwned k-anonymity API, or an offline list), hashed with Argon2id. | Must |
| TR-AUTH-8 | Verification and reset codes: 6 digits, hashed when stored, valid 15 min, 5 attempts. Kept in `temp` with a TTL index. | Must |
| TR-AUTH-9 | Multi-factor sign-in (TOTP authenticator app) is **required** for `admin` accounts; admin sessions last at most 8 h. | Must |

### 4.3 Data (MongoDB)
| ID | Requirement | Priority |
|---|---|---|
| TR-DATA-1 | One `inventory` database. Each service connects with its **own MongoDB user**, which can only use the collections that service owns (custom roles). | Must |
| TR-DATA-2 | Existing collection names are kept. New collections: `organisations`, `auditlog`. | Must |
| TR-DATA-3 | **Writes:** write concern `majority` and `retryWrites=true`. **Reads:** `primary` for transactional reads; `secondaryPreferred` only for reports and backups. | Must |
| TR-DATA-4 | Multi-document transactions are used only where one change spans several documents (e.g. reserving several storage units for a request), and are kept under 1 s. | Must |
| TR-DATA-5 | Every query must use an index. CI runs `explain()` on each repository query against the seeded test data and fails if any query scans the whole collection. | Must |
| TR-DATA-6 | Collection schemas are enforced with `$jsonSchema` validators (`validationLevel: moderate` during migration, `strict` after). | Should |
| TR-DATA-7 | Status changes are made with conditional updates (`filter` includes the expected current `status`); a `409` is returned if the document has already moved on. | Must |
| TR-DATA-8 | Outgoing events are written to an `outbox` array on the changed document in the **same write**. A relay publishes them to Kafka and marks them sent. | Must |
| TR-DATA-9 | Product search uses a MongoDB **text index** (name, make, modelname, modelnumber, keywords) plus prefix indexes on serials. Unanchored `$regex` searches are not allowed. | Must |
| TR-DATA-10 | `auditlog` can only be added to: no service account has update or delete rights on it. | Must |
| TR-DATA-11 | All timestamps are stored as UTC `Date` values and displayed in America/Barbados time. | Must |
| TR-DATA-12 | Money is stored as `Decimal128` in BBD. Quotes record their `currency` (BBD/USD) and, for USD, the `exchangeRate` staff entered. | Must |

### 4.4 Messaging (Kafka)
| ID | Requirement | Priority |
|---|---|---|
| TR-MSG-1 | Topics: `identity.user.events`, `catalog.product.events`, `inventory.stock.events`, `order.events`, `document.events`, `media.jobs`, `media.results`, `audit.events`, each with a `.retry` and a `.dlq` topic. | Must |
| TR-MSG-2 | The message key is the entity ID (`userId`, `productId`, `orderId`), so all events for one entity are processed in order. | Must |
| TR-MSG-3 | Every event uses the standard envelope (`eventId, type, version, occurredAt, correlationId, actorId, payload`), and its schema is registered in Apicurio. | Must |
| TR-MSG-4 | Producers: idempotent producer, `acks=all`. Topics: replication factor 3, `min.insync.replicas=2`. | Must |
| TR-MSG-5 | Each service has its own consumer group. Consumers are idempotent (they record processed `eventId`s in Redis for 7 days, or check versions). | Must |
| TR-MSG-6 | Failed messages are retried with backoff (1 min, 5 min, 30 min), then sent to the DLQ. Any message in a DLQ triggers an alert. | Must |
| TR-MSG-7 | Retention 7 days by default. `identity.user.events` and `catalog.product.events` are compacted (only the latest event per key is kept). | Should |

### 4.5 Files
| ID | Requirement | Priority |
|---|---|---|
| TR-FILE-1 | Files are stored on a **local Docker volume** on the main host (`/srv/sia-data`). No cloud object storage. | Must |
| TR-FILE-2 | Stored names are random UUIDs; original name, MIME type, size, SHA-256 hash and owner are recorded in `orders.files[]` / product metadata. | Must |
| TR-FILE-3 | Uploads: PDF, JPEG, PNG and WebP only. The file content is checked to confirm its type, not just its extension. Limit 20 MB. Images are re-encoded to remove embedded metadata (EXIF). | Must |
| TR-FILE-4 | Protected files are served by nginx after the API checks permission and replies with `X-Accel-Redirect`. Their folder is never directly reachable. | Must |
| TR-FILE-5 | Public product images are served directly by nginx with long-lived cache headers. A resized WebP version is generated for each image. | Should |
| TR-FILE-6 | The volume is backed up nightly to offsite storage (TR-OPS-3). | Must |

### 4.6 Email and notifications
| ID | Requirement | Priority |
|---|---|---|
| TR-MAIL-1 | Email is sent only by notification-svc, triggered by Kafka events, through the **CIMH mail server** (authenticated SMTP over TLS). | Must |
| TR-MAIL-2 | Sending domain set up with SPF, DKIM and DMARC records so mail isn't marked as spam. | Must |
| TR-MAIL-3 | HTML + plain-text Jinja2 templates; every value is HTML-escaped (the current code builds HTML with f-strings). | Must |

## 5. Non-functional requirements

| ID | Area | Requirement | Priority |
|---|---|---|---|
| TR-PERF-1 | Latency | p95 < **300 ms**, p99 < **1 s** for catalogue, search and request reads at 1,000 req/s | Must |
| TR-PERF-2 | Latency | p95 < **500 ms** for requests that change state (excluding file uploads) | Must |
| TR-PERF-3 | Throughput | Sustain 1,000 req/s for 30 min in a load test with an error rate < 0.1% | Must |
| TR-PERF-4 | Frontend | SHOP home and product pages: Largest Contentful Paint < 2.5 s on 4G. Initial JavaScript < 250 KB compressed, with each route loaded only when needed | Should |
| TR-SCALE-1 | Horizontal | Services hold no state, so `docker compose up --scale <svc>=N` works with no code change | Must |
| TR-SCALE-2 | Pools | MongoDB pool ≤ 50 connections per container; total stays under the server's connection limit | Must |
| TR-AVAIL-1 | Uptime | 99.5% per month for SHOP and SIA (excluding announced maintenance) | Must |
| TR-AVAIL-2 | Failover | Loss of any one MongoDB member or one Kafka broker: no data loss, and writes resume within 30 s | Must |
| TR-REC-1 | RPO / RTO | RPO ≤ 24 h, RTO ≤ 4 h after total loss of the main host | Must |
| TR-SEC-1 | Transport | TLS 1.2+ only, HSTS, security headers (CSP, X-Content-Type-Options, frame-ancestors, Referrer-Policy) | Must |
| TR-SEC-2 | Secrets | Secrets are never in git or in images. Provided as Docker secrets / `.env` files with `0600` permissions; rotated at least yearly and immediately after any exposure | Must |
| TR-SEC-3 | Scanning | CI runs dependency scanning (pip-audit, `npm audit`), static analysis (Semgrep, Bandit), image scanning (Trivy) and secret scanning (gitleaks). High or critical findings block the merge | Must |
| TR-SEC-4 | Database | Replica set members authenticate to each other with keyfile/x.509 and talk over TLS. MongoDB, Kafka and Redis are not exposed outside the private network | Must |
| TR-SEC-5 | Rate limits | nginx: 20 req/s per IP for the API in general; 5 req/min for auth endpoints. A second Redis-based limit per account | Must |
| TR-SEC-6 | Malware | Every upload is scanned with **ClamAV** (clamd container, signatures updated daily) before it becomes downloadable; infected files are quarantined and staff alerted | Must |
| TR-SEC-7 | Messaging and cache auth | Kafka **SASL/SCRAM** with per-service principals and **topic ACLs** (only the owning service may produce to its topics); Redis **ACL users** with passwords | Must |
| TR-SEC-8 | Container hardening | Containers run as non-root with a read-only root filesystem, `cap_drop: [ALL]`, `no-new-privileges`, no Docker socket mounts; only media-worker gets GPU access | Must |
| TR-SEC-9 | Image signing | CI signs images with **cosign**; deploy verifies signatures before `docker compose pull` | Must |
| TR-SEC-10 | Disk encryption | Raspberry Pi SSDs (and the host data disks where feasible) use **LUKS** full-disk encryption | Must |
| TR-SEC-11 | Mobile hardening | SIA Mobile: HTTPS only (`cleartextTrafficPermitted=false`), **certificate pinning** to the CIMH/Let's Encrypt intermediates, **app lock** with the device credential after 5 min inactivity | Must |
| TR-SEC-12 | Network segmentation | The main host and both Pis sit on a **dedicated VLAN** (set up by CIMH IT); MongoDB 27017 is reachable only between those three machines | Must |
| TR-OBS-1 | Logs | Logs are JSON lines that include `traceId`, `service` and `userId`. No passwords, tokens or full personal data in logs | Must |
| TR-OBS-2 | Metrics | Each service exposes request rate, errors and duration (RED metrics), plus Kafka consumer lag and MongoDB pool usage, at `/metrics` | Must |
| TR-OBS-3 | Alerts | Alerts for: security events (> 20 failed logins/min, admin lockout, admin login from a new IP, refresh-token reuse, 403/404 spikes from one user, ClamAV detection), any new unhandled exception type, host memory > 85%, error rate > 1%, p95 above target, DLQ not empty, consumer lag > 1,000, replica set member down, disk > 80%, certificate expiring < 14 days | Must |
| TR-ACC-1 | Accessibility | WCAG 2.1 AA for SHOP and SIA. axe-core checks run in CI on key pages | Should |
| TR-COMP-1 | Browsers | The last 2 versions of Chrome, Edge, Firefox and Safari; Safari on iOS 16+; Chrome on Android | Must |
| TR-I18N-1 | Locale | English only; dates shown as `dd MMM yyyy`; currency shown with its code (`BBD 1,250.00`) | Must |
| TR-PRIV-1 | Privacy | Rejected and expired accounts are deleted after 90 days; personal data can be exported on request | Should |

## 6. Hardware and infrastructure

### 6.1 Machines
| Machine | Minimum specification | Runs |
|---|---|---|
| **Main host** | **16 CPU cores, 32 GB RAM, 2 × GPU (6 GB VRAM each)**, 2 × 2 TB NVMe (RAID 1), 1 Gbps network, Ubuntu Server (latest LTS), NVIDIA driver + NVIDIA Container Toolkit | nginx, all services (scaled), media-worker (GPU), Kafka ×3, Apicurio, Redis, MongoDB **primary**, monitoring stack, staging, file volume |
| **Raspberry Pi A** | **Raspberry Pi 5, 8 GB** (16 GB recommended), **1 TB NVMe SSD** via M.2 HAT, active cooling, official 27 W power supply, Ubuntu Server latest LTS (arm64) | MongoDB **secondary** (priority 1), node exporter |
| **Raspberry Pi B** | Same as Pi A | MongoDB **secondary** (priority 1), runs the **backup job**, node exporter |
| **UPS** | Covers all three machines for ≥ 15 min, with clean automatic shutdown | Protects against power loss |
| **Offsite backup target** | **Another CIMH site**, reachable by restic over the network | Encrypted backups |

### 6.2 Known limits of this layout
- Kafka's three brokers all run on the main host. They protect against a broker *process* failing, but not against the host failing. If the host is down, SHOP and SIA are down anyway, because the services also run there.
- If the main host fails, MongoDB keeps all data on the Pis, but the platform is unavailable until the host is restored or rebuilt (TR-REC-1).
- The Pis must be on the same LAN as the host, with fixed IPs, and the network latency between them must be under 2 ms.

### 6.3 Main host memory budget (32 GB)

| Component | RAM (approx.) |
|---|---|
| Operating system + Docker | 2 GB |
| MongoDB primary (WiredTiger cache 6 GB) | 8 GB |
| Kafka x 3 brokers (1 GB heap each + page cache) | 5 GB |
| Redis, Apicurio, nginx | 2 GB |
| Services (6 x 2 replicas x ~250 MB) | 3 GB |
| media-worker (models mostly in GPU memory) | 2 GB |
| Prometheus, Alertmanager, exporters | 2 GB |
| ClamAV (clamd) | 1–1.5 GB |
| **Subtotal (production)** | **25–25.5 GB** |
| Staging Compose project (reduced: 1 Kafka broker, 1 replica per service, MongoDB cache 1 GB) | 4-6 GB |
| **Total** | **29.5–31.5 GB of 32 GB** (very tight; see note) |

**This only just fits.** ClamAV (TR-SEC-6) adds 1–1.5 GB, so a **64 GB upgrade is strongly recommended** before go-live. To keep it safe:
- Every container has a memory limit (`mem_limit`) so one component cannot starve the others.
- Staging is **stopped during production load peaks and while load tests run against production-sized data**. Load tests at full scale (TR-PERF-3) are run with staging as the only active stack, outside business hours.
- If memory use stays above 85% (alert), the first step is upgrading the host to 64 GB.

### 6.4 GPUs
The two 6 GB GPUs are used by **media-worker** for background removal (rembg/onnxruntime-gpu) and image processing. One media-worker replica is pinned to each GPU through Compose `deploy.resources.reservations.devices`. If a GPU is unavailable, the worker falls back to the CPU.

## 7. Environments

| Environment | Where | Data | Purpose |
|---|---|---|---|
| **Local** | Developer machine, `docker compose -f compose.dev.yml` | Seeded test data (single-node replica set, 1 Kafka broker) | Development |
| **CI** | GitHub Actions runners | Temporary containers created per test run | Tests |
| **Staging** | The **main host**, in a separate Compose project with lower resource limits | Anonymised copy of production | Acceptance testing, migration dry-runs, load tests |
| **Production** | Main host + 2 Pis | Live | Live service |

## 8. Source control and CI/CD

| ID | Requirement | Priority |
|---|---|---|
| TR-CI-1 | Git on GitHub. **SHOP and SIA are put under source control** (SHOP currently has no repository). Build output (e.g. `SHOP/store/`) and data files (PDFs, `.db`, logs, `.env`) are never committed. | Must |
| TR-CI-2 | Repository layout: one repository (`services/*`, `web/*`, `packages/*`, `deploy/*`, `docs/*`) plus the existing Android repository. | Should |
| TR-CI-3 | Trunk-based development: short-lived branches, a PR with 1 approving review, and all CI checks passing before merge. | Must |
| TR-CI-4 | **CI pipeline:** lint → type-check → unit tests → integration tests (testcontainers) → contract tests → security scans → build images, tagged with the commit SHA → push to GHCR. | Must |
| TR-CI-5 | **CD pipeline:** deploy to staging automatically on merge. Production is deployed by manual approval: `docker compose pull && docker compose up -d`, one service at a time, waiting for each to pass its health check. | Must |
| TR-CI-6 | Test coverage: ≥ 80% lines for service business logic; every PRD requirement has at least one automated test (tracked in the RTM). | Should |
| TR-CI-7 | Database migrations are versioned scripts (e.g. `mongodb-migrations` / custom runner), run once per release before services start. | Must |

## 9. External integrations

| System | Use | Requirement |
|---|---|---|
| CIMH mail server | All email | Authenticated SMTP over TLS; SPF/DKIM/DMARC configured for the sending domain |
| Carriers (FedEx, DHL) | None | No integration. Tracking numbers are entered manually by staff; the request page shows a link to the carrier's public tracking page |
| Have I Been Pwned (Pwned Passwords) | Breached-password check | k-anonymity API: only a short hash prefix is sent, never the password; if the service is unavailable, sign-up continues without the check |

## 10. Constraints

1. **Docker Compose only:** no Kubernetes or other orchestrator.
2. **Local file storage only:** no S3 or other cloud object storage.
3. **No online payments.**
4. **MongoDB is required** as the main database; one `inventory` database; existing collection names are kept.
5. **nginx** is the only edge component (no cloud CDN or WAF).
6. MongoDB secondaries run on Raspberry Pi 5 (ARM64). All images used on the Pis must have `linux/arm64` builds.
7. The current Flask API stays live alongside the new services until all clients have migrated (PRD M9). nginx routes traffic to old or new per route group.

## 11. Questions

| # | Question | Outcome |
|---|---|---|
| 1 | Minimum Android version? | **Resolved:** Android 11 (API 30). |
| 2 | Sentry self-hosted or SaaS? | **Resolved:** neither. Sentry is removed; errors are tracked through logs and Prometheus metrics/alerts. |
| 3 | Offsite backup target? | **Resolved:** another CIMH site. |
| 4 | SMTP relay? | **Resolved:** the CIMH mail server. |
| 5 | Source control and CI? | **Resolved:** GitHub + GitHub Actions. |
| 6 | Main host specification? | **Resolved:** 16 cores, 32 GB RAM, 2 x 6 GB GPU. |
| 7 | Staging location? | **Resolved:** the main host. |
| 8 | Does everything fit in 32 GB RAM? | **Resolved:** only just: 29.5–31.5 GB including ClamAV (section 6.3). A 64 GB upgrade is strongly recommended. |
| 9 | Does the CIMH mail server allow authenticated SMTP from the app host, and can SPF/DKIM be set up for the sending address? | **Resolved:** yes. |
| 10 | Is there network connectivity and storage capacity at the other CIMH site for ~1.5 TB/year of backups? | **Resolved:** yes. |
