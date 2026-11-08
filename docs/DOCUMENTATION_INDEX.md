# CIMH Stores Platform: Documentation Index

Every document to be produced for the CIMH Stores Platform (SHOP · SIA · SIA Mobile), grouped by project phase. Each entry gives a technical definition, its purpose, its audience, its required contents and its planned file.

| Status key | Meaning |
|---|---|
| ✅ Draft | Started; see file |
| ⬜ Planned | Not started |

---

## Summary

| # | Document | Abbr. | Phase | File | Status |
|---|---|---|---|---|---|
| 1 | Product Requirements Document | PRD | Before | [PRD.md](PRD.md) | ✅ Draft |
| 2 | Technical Requirements Document | TRD | Before | [TRD.md](TRD.md) | ✅ Draft |
| 3 | Technical Architecture Document + ADRs | TAD | Before | [TAD.md](TAD.md), `adr/` | ✅ Draft (ADR files pending) |
| 4 | Background (Backend) Schema Document | BSD | Before | [BSD.md](BSD.md) | ✅ Draft |
| 5 | API Specification + Event Specification | API | Before | [api/README.md](api/README.md), `api/*.openapi.yaml`, `api/events.asyncapi.yaml` | ✅ Draft (validated) |
| 6 | App Flow Document | APD | Before | [APD.md](APD.md) | ✅ Draft |
| 7 | Design Brief Document | DBD | Before | [DESIGN_BRIEF.md](DESIGN_BRIEF.md) | ✅ Draft |
| 8 | Security and Threat Model | STM | Before | [SECURITY.md](SECURITY.md) | ✅ Draft |
| 9 | Data Migration Plan | DMP | Before | [MIGRATION_PLAN.md](MIGRATION_PLAN.md) | ✅ Draft |
| 10 | Infrastructure and Environment Plan | IEP | Before | [INFRASTRUCTURE.md](INFRASTRUCTURE.md) | ✅ Draft |
| 11 | Test Strategy | TS | Before | [TEST_STRATEGY.md](TEST_STRATEGY.md) | ✅ Draft |
| 12 | Implementation Plan | IP | Before | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | ✅ Draft |
| 13 | Coding Standards and Contribution Guide | CSG | Before | `CONTRIBUTING.md` | ⬜ Planned |
| 13a | System Manual (written documentation + draw.io diagrams) | — | Before → After (living) | [manual/index.html](manual/index.html) | ✅ Draft |
| 14 | Service / App READMEs | — | During | `<service>/README.md` | ⬜ Planned |
| 15 | Generated API Reference | — | During | auto (`/docs` per service) | ⬜ Planned |
| 16 | Test Plans and Test Cases | TP | During | `testing/` | ⬜ Planned |
| 17 | Requirements Traceability Matrix | RTM | During | `RTM.md` | ⬜ Planned |
| 18 | Changelog and Release Notes | — | During | `CHANGELOG.md` | ⬜ Planned |
| 19 | Migration Dry-run Reports | — | During | `migration/` | ⬜ Planned |
| 20 | Load and Security Test Reports | — | During | `reports/` | ⬜ Planned |
| 21 | Deployment / Release Run Book | — | After | `runbooks/DEPLOYMENT.md` | ⬜ Planned |
| 22 | Operations Run Book | — | After | `runbooks/OPERATIONS.md` | ⬜ Planned |
| 23 | Backup and Disaster Recovery Plan | DRP | After | `runbooks/DISASTER_RECOVERY.md` | ⬜ Planned |
| 24 | Monitoring and Alerting Guide | — | After | `runbooks/MONITORING.md` | ⬜ Planned |
| 25 | Incident Response Plan + Post-mortem Template | IRP | After | `runbooks/INCIDENT_RESPONSE.md` | ⬜ Planned |
| 26 | User Guides (SHOP, SIA, Mobile) | — | After | `guides/` | ⬜ Planned |
| 27 | Admin Guide | — | After | `guides/ADMIN.md` | ⬜ Planned |
| 28 | Training Material | — | After | `training/` | ⬜ Planned |
| 29 | Service Level and Support Policy | SLA | After | `SUPPORT_POLICY.md` | ⬜ Planned |
| 30 | Privacy Policy and Terms of Use | — | After | `legal/` | ⬜ Planned |
| 31 | Handover and Maintenance Guide | — | After | `HANDOVER.md` | ⬜ Planned |
| 32 | Project Close-out and Lessons Learned | — | After | `CLOSEOUT.md` | ⬜ Planned |

**Recommended writing order:** PRD → TRD → TAD → BSD → API → APD → Design Brief → Security → Migration → Infrastructure → Test Strategy → Implementation Plan.

**How the planning documents depend on each other:**
- The PRD defines *what* the product does.
- The TRD and TAD define *with what* and *how*.
- The BSD and API specification turn those into exact data and contracts.
- The APD and Design Brief define the user experience.
- The Implementation Plan puts all of the above into order.

---

## Phase 1: Before the build (planning and design)

### 1. Product Requirements Document (PRD) ✅
**Definition:** Describes what the product does, feature by feature, and the expected functionality and behaviour of the website and apps. Uses Atlassian's PRD structure.
**Purpose:** The single agreed source of *what* is being built and why, against which everything else is designed and tested.
**Audience:** Product owner, stakeholders, developers, QA, design.
**Contents:** Project details (owner, status, target release); objective; success metrics; background and strategic fit; assumptions; requirements as numbered user stories with priority (Must/Should/Could) and notes; user interaction and design; questions and outcomes; not doing (out of scope).
**File:** [PRD.md](PRD.md)

### 2. Technical Requirements Document (TRD)
**Definition:** Defines the tools, techniques and infrastructure used to build the platform, and the technical requirements each part must meet. It keeps everyone aligned on the stack.
**Purpose:** Turns the PRD's product needs into measurable technical requirements and fixes the technology choices before design detail begins.
**Audience:** Developers, DevOps, tech lead, security reviewer.
**Contents:**
- **Technology stack, with versions:** FastAPI (Python 3.12+), Vue 3 + TypeScript (Vite, Pinia, Vue Router, Vuetify), Kotlin/Jetpack Compose (Android), MongoDB replica set, Kafka (KRaft), Redis, nginx, Docker Compose.
- **Libraries and tooling:** PyMongo Async/Beanie, aiokafka, Pydantic, pytest, Vitest, Playwright, ESLint, Ruff, mypy.
- **Non-functional requirements as numbers:**
  - Performance: p95 latency, throughput.
  - Scale: 1M users.
  - Availability: 99.5%.
  - Recovery: maximum data loss (RPO) and maximum time to restore (RTO).
  - Security, accessibility, supported browsers and Android versions.
- **Hardware requirements:** the main host, plus 2 × Raspberry Pi 5 (8 GB, SSD).
- **Environments** (development, staging, production), source control, CI/CD tooling.
- **Integration requirements:** SMTP, FedEx, DHL.
- **Constraints:** local file storage only, no payments, Docker Compose only.

**File:** `TRD.md`

### 3. Technical Architecture Document (TAD) + Architecture Decision Records (ADRs)
**Definition:** Explains how the system is built: what the parts are, how they connect, and why it was designed that way. The ADRs are short records of individual design decisions, each with its context, the options considered, the decision and its consequences.
**Purpose:** The engineering blueprint, used to build, review and maintain the system consistently.
**Audience:** Developers, DevOps, security reviewers, new team members.
**Contents:**
- Context and system boundary.
- Architecture diagrams at increasing detail (C4 model: system context → containers → components).
- **Service catalogue:** for identity, catalog, inventory, order, document and notification services and the media worker, each one's responsibility, the collections it owns, its APIs, the events it publishes and consumes, and how it scales.
- **Communication:** HTTP calls through nginx; Kafka topics, message keys, partitions, the outbox relay, retries and the DLQ.
- **Data architecture summary** (detail lives in the BSD), including when transactions are used.
- **Security architecture:** login tokens, revocation, roles, ownership checks, TLS, secrets.
- **Key workflow diagrams:** registration and approval; request → quote (supplier + CIMH stock) → accept; reservation; stow/pick.
- **Deployment view:** the main host plus 2 Pis, the Compose project per host, networks and volumes.
- Observability.
- Risks and technical debt.
- Index of ADRs.

**File:** `TAD.md`, `adr/0001-*.md`…

### 4. Background (Backend) Schema Document (BSD)
**Definition:** Defines where client data lives, how it is structured, who can access it, and the key relationships between data.
**Purpose:** The single source of truth for the data model, used by service developers, the migration and security reviews.
**Audience:** Backend developers, DBA, security reviewer, migration team.
**Contents:**
- **Data locations:** the `inventory` database on the replica set; the file volume.
- **Collection ownership by service:**
  - identity: `accounts`, `temp`, `organisations`, `auditlog`
  - catalog: `product`, `xuser`, `misc`
  - inventory: `storage`, `history`, `stock` (new)
  - order: `orders`
- **Per collection:**
  - Field-level schema (name, type, required, validation).
  - Example document.
  - Indexes, including unique and TTL indexes.
  - Size and growth estimates.
- **Relationships:** e.g. `storage.product → product.id`; `storage.orderid → orders.id`; `orders.customer → accounts.id`; `accounts.organisationId → organisations.id`.
- **Access rules:** which service and which role may read or write which fields (personal data, `cost`, passwords).
- **Status models:** account status, paid request status, Pro Bono request status.
- **Data rules:** data retention and deletion; audit records that can only be added to; which document types use transactions.
- **Change history** of the schema.

**File:** `BSD.md`

### 5. API Specification (OpenAPI) + Event Specification (AsyncAPI)
**Definition:** The exact contract for every endpoint: what you send and what you get back. The Event Specification does the same for Kafka messages.
**Purpose:** Lets frontend, mobile and backend developers build in parallel against a fixed, testable contract. Client code and TypeScript types can be generated from it.
**Audience:** Developers of SHOP, SIA, the Android app and each service; QA.
**Contents:**
- **Conventions:** base paths (`/api/identity`, `/api/catalog`, `/api/inventory`, `/api/orders`, `/api/documents`); versioning; date (ISO-8601 UTC) and currency (BBD/USD) formats; cursor paging; an error format based on RFC 9457; rate limits; making retried requests safe to repeat.
- **Authentication:** cookies and tokens for web; tokens for mobile; refresh, logout and CSRF; which roles can call each endpoint.
- **Per endpoint:** method, path, parameters, request and response schemas, status codes (`401`, `403`, `404`, `409` conflict, `422` invalid input, `429` rate limited), required role, examples.
- **Shared data types:** Account, Organisation, Product, StorageUnit, OrderRequest, Quote, CimhQuote, Shipment, Document.
- **Events:** topic, key, envelope (`eventId, type, version, occurredAt, correlationId, actorId, payload`) and payload schema.
- Changelog and deprecation policy.

**File:** `api/<service>.openapi.yaml`, `api/events.asyncapi.yaml`

### 6. App Flow Document (APD)
**Definition:** Shows what happens when someone clicks and which page comes next. Maps the main user journeys through the website and mobile app.
**Purpose:** Gives design, frontend and QA one shared map of screens, navigation and decision points, so no journey or edge case is missed.
**Audience:** Designers, frontend and mobile developers, QA, product owner.
**Contents:**
- **Site map** for each app: SHOP, SIA, Mobile.
- **Flow diagram per journey:**
  - Register → verify → awaiting approval → approved → log in
  - Browse/search → product → cart → submit (with automatic split of paid and Pro Bono items)
  - Quote review → choose CIMH or supplier per item → accept/decline
  - Staff request desk
  - Admin approvals
  - Warehouse scan → stow/pick
- **Per screen:** its entry points, actions, the next screen, error and empty states, and which roles can see it.
- **Guards:** e.g. `@cimh.edu.bb` accounts cannot use the cart; customers only see their organisation's requests.
- **Notification triggers** shown on each flow.

**File:** `APD.md`

### 7. Design Brief Document
**Definition:** Defines the visual design direction for the website and apps, including colours, fonts and how each screen should look, so the experience is consistent and on-brand.
**Purpose:** Gives designers and frontend developers one visual standard across SHOP, SIA and Mobile.
**Audience:** Designers, frontend and mobile developers, stakeholders.
**Contents:**
- Brand basis (CIMH logo and colours).
- **Design tokens:** colours for light and dark themes, typography, spacing, border radius, elevation.
- Vuetify theme configuration and Android Material 3 theme to match.
- **Component library:** buttons, forms, cards, tables, status chips for each request and account status, the quote comparison view.
- **Per screen:** layout guidance and key screen mock-ups.
- Icons and imagery (product photo standards).
- Responsive breakpoints.
- Accessibility (WCAG 2.1 AA contrast, focus, sizes).
- Tone of voice for UI text and emails; email template design.

**File:** `DESIGN_BRIEF.md`

### 8. Security and Threat Model
**Definition:** A systematic analysis of what needs protecting, the threats against it, and the controls that reduce each threat, usually using STRIDE. STRIDE covers six threat types: Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege.
**Purpose:** Makes sure security is designed in, and gives the pre-launch security review something to check against.
**Audience:** Tech lead, developers, security reviewer, admins.
**Contents:**
- **Assets:** personal data, accounts, quotes, invoices, stock.
- **Trust boundaries and data-flow diagrams.**
- **STRIDE threats** per component, each with its control:
  - Code injection, as found today with `eval`.
  - Users reading other users' data by changing an id (IDOR).
  - Credential stuffing (attackers trying leaked passwords).
  - Regex denial of service (ReDoS).
  - File upload abuse.
- **Secrets management**, including rotating the credentials currently exposed in `.env` and in chat.
- **Role and permission matrix.**
- Logging and audit.
- Data privacy obligations.
- Vulnerability management (dependency scanning).

**File:** `SECURITY.md`

### 9. Data Migration Plan
**Definition:** A plan for moving existing data (reference DB on 172.16.0.203: 83 products, 697 storage units, 39 orders, 65 accounts, 860 history, `misc`) from the current structure into the new one, with checks and a way to roll back.
**Purpose:** Gets data into v2 without loss or downtime surprises.
**Audience:** Backend developers, DBA, tech lead.
**Contents:**
- Source-to-target field mapping.
- **Transformations:**
  - `sellable` from string to boolean.
  - Carts moved out of `accounts`.
  - `misc` split into separate document kinds.
  - Status mapping: open → `SUBMITTED`, complete → `DELIVERED`, cancelled → `CANCELLED`.
  - Existing accounts → `ACTIVE`.
- New indexes; copying in batches for `storage`.
- Checks: document counts and checksums.
- Dry-run schedule; the cut-over steps; the rollback plan.

**File:** `MIGRATION_PLAN.md`

### 10. Infrastructure and Environment Plan
**Definition:** Specifies the machines, networks, containers and environments the platform runs on.
**Purpose:** Lets DevOps build, rebuild and scale the platform the same way every time.
**Audience:** DevOps, tech lead.
**Contents:**
- Machine specifications: the main host, and the two Raspberry Pi 5s with SSDs.
- Network: fixed IPs or local DNS, firewall rules, TLS certificates.
- Compose projects per host: services, scaling, volumes, networks.
- Kafka and replica set layout.
- Environments: dev, staging, production.
- Secrets distribution.
- Capacity estimates.

**File:** `INFRASTRUCTURE.md`

### 11. Test Strategy
**Definition:** The overall approach to checking quality: test types, tools, test coverage targets, environments and the criteria for passing.
**Purpose:** Agrees how "done" and "ready to launch" are proved.
**Audience:** QA, developers, product owner.
**Contents:**
- **Test types:**
  - Unit tests.
  - Integration tests, including Kafka and MongoDB.
  - **Contract tests** that check implementations match the API specification.
  - End-to-end tests with Playwright, plus Android UI tests.
  - Load tests with k6/Locust against the 1M-user target.
  - Security tests (static analysis, dependency scanning, dynamic scanning).
  - Accessibility tests.
  - Migration tests.
- Coverage targets.
- Test data, including anonymising copies of real data.
- Defect severity definitions.
- Pass/fail criteria for each stage.

**File:** `TEST_STRATEGY.md`

### 12. Implementation Plan
**Definition:** Outlines what gets built and in what order, breaking the project into clear phases with key deliverables.
**Purpose:** Keeps delivery sequenced, estimated and trackable.
**Audience:** Product owner, tech lead, team, stakeholders.
**Contents:**
- **Phases**, each with its deliverables, the PRD requirements it covers, its dependencies and the conditions for calling it finished:
  - Phase 0: security hot-fixes to the current app.
  - Phase 1: foundations (Compose, replica set, Kafka, CI/CD).
  - Phase 2: identity and approvals.
  - Phase 3: catalog.
  - Phase 4: inventory.
  - Phase 5: orders and quotes.
  - Phase 6: documents and notifications.
  - Phase 7: SHOP and SIA frontends rebuilt in TypeScript.
  - Phase 8: mobile app moved to the new API.
  - Phase 9: migration and cut-over.
  - Phase 10: retiring the Flask app.
- Milestones and timeline.
- Team and roles.
- Risks and how they are reduced.

**File:** `IMPLEMENTATION_PLAN.md`

### 13. Coding Standards and Contribution Guide
**Definition:** The rules for writing, reviewing and merging code.
**Purpose:** Keeps a codebase written by several people and services consistent and reviewable.
**Audience:** All developers.
**Contents:**
- Python and TypeScript/Kotlin style rules and the tools that enforce them (Ruff, mypy, ESLint, Prettier, ktlint).
- Repository layout (one repository for all services, or one per service).
- Branching model and commit message format.
- Pull-request template and review checklist.
- Testing requirements for each PR.
- How to manage secrets and dependencies.

**File:** `CONTRIBUTING.md`

---

## Phase 2: During the build

### 14. Service / App READMEs
**Definition:** A short document at the root of each service or app repository folder.
**Purpose:** Gets a developer from a fresh checkout to a running, tested component quickly.
**Contents:** Purpose; prerequisites; environment variables; how to run, test and build; the events and APIs it owns; links to the TAD, API and BSD.

### 15. Generated API Reference
**Definition:** Interactive API documentation generated automatically from each FastAPI service's code (Swagger UI / ReDoc at `/docs`).
**Purpose:** Always-current documentation of the running code. CI checks it against the API Specification (#5) to catch drift.

### 16. Test Plans and Test Cases
**Definition:** For each release, the tests to run (the plan) and the step-by-step cases, each with its expected result.
**Purpose:** Repeatable proof that each PRD requirement works.
**Contents:** Scope and schedule for each release; test cases referencing PRD IDs (A1, O5a, I9…); test results and the defects raised.

### 17. Requirements Traceability Matrix (RTM)
**Definition:** A table linking each PRD requirement to the code, tests and status that implement it.
**Purpose:** Shows that nothing has been missed and that every requirement is tested.
**Contents:** Requirement ID → TAD section → endpoint/event → issue or PR → test cases → status.

### 18. Changelog and Release Notes
**Definition:** The changelog is a running, dated list of changes per version (Keep a Changelog format with semantic version numbers). Release notes are the user-facing summary of each release.
**Purpose:** Tells developers and users what changed.

### 19. Migration Dry-run Reports
**Definition:** The results of each rehearsal of the data migration.
**Purpose:** Proves the migration is correct and measures how long it takes before the real cut-over.
**Contents:** Run date; data volume; duration; count and checksum comparisons; issues found and fixed.

### 20. Load and Security Test Reports
**Definition:** The results of performance tests and security tests (static analysis, dependency scanning, dynamic scanning, optional penetration test).
**Purpose:** Evidence that the platform meets the TRD targets and the security bar before launch.
**Contents:** Test setup; results compared with targets (latency, throughput, errors); findings with severity; how each was fixed and re-tested.

---

## Phase 3: After the build (launch and operations)

### 21. Deployment / Release Run Book
**Definition:** A step-by-step procedure for deploying a release and switching over from the Flask system.
**Purpose:** Safe, repeatable go-lives with a known way back.
**Contents:** Pre-flight checklist; deployment steps per host; the nginx route switch-over (moving one route group at a time off Flask); smoke tests; rollback steps; who signs off.

### 22. Operations Run Book
**Definition:** Procedures for routine and known operational tasks.
**Purpose:** Lets any operator run the platform without the original developers.
**Contents:**
- Starting, stopping and scaling services.
- Kafka: replaying messages from the DLQ, managing consumer lag.
- Replica set: checking health, what to do when a Pi takes over as primary.
- Disk space; renewing TLS certificates; rotating logs.
- Rotating secrets; doing an account cleanup.

### 23. Backup and Disaster Recovery Plan
**Definition:** How data is backed up, and how the service is restored after losing a node, a host or the data itself.
**Purpose:** Meets the RPO (≤ 24 h) and RTO (≤ 4 h) targets set in the PRD.
**Contents:** Backup schedule and retention (MongoDB taken from a Pi secondary, plus the file volume, copied offsite); restore steps; failure scenarios (host down, Pi down, disk failure, corruption, ransomware); quarterly restore-test log.

### 24. Monitoring and Alerting Guide
**Definition:** A description of the dashboards, metrics, logs and alerts, and what to do when each alert fires.
**Purpose:** Problems are noticed and acted on quickly.
**Contents:** Useful Prometheus queries; Alertmanager alert rules and thresholds (errors, latency, consumer lag, replica set health, disk, memory); how to read and search container logs (`docker compose logs` + `jq`, following a `traceId`); who is on call and how issues escalate.

### 25. Incident Response Plan + Post-mortem Template
**Definition:** The process for detecting, handling, communicating about and learning from outages and security incidents.
**Purpose:** Calm, consistent handling of incidents and steady improvement afterwards.
**Contents:** Severity levels; roles; communication templates; data-breach notification duties; a blame-free post-mortem template (timeline, cause, impact, actions).

### 26. User Guides
**Definition:** Task-based instructions for end users, one guide per app.
**Purpose:** Users can complete their tasks without needing support.
**Contents:**
- **SHOP (customers):** register, browse, request, review and accept quotes, track requests.
- **SIA (staff):** request desk, quoting, purchasing, shipping, inventory.
- **Mobile (warehouse):** scan, stow, pick.

### 27. Admin Guide
**Definition:** Instructions for administrator-only functions.
**Purpose:** Admins can govern the platform correctly.
**Contents:** Account approvals; organisations (create and merge); roles; suspensions; email lists; admin fee; Pro Bono item limits; departments, types and projects; reading the audit log.

### 28. Training Material
**Definition:** Material for onboarding staff and admins.
**Purpose:** Fast, consistent adoption at launch.
**Contents:** Quick-reference cards; walkthrough videos or slides; practice exercises in a training environment.

### 29. Service Level and Support Policy
**Definition:** The service commitments and how users get help.
**Purpose:** Sets clear expectations for availability and response times.
**Contents:** Availability target (99.5%); support hours and channels; response and resolution times by severity; maintenance windows.

### 30. Privacy Policy and Terms of Use
**Definition:** The legal texts for SHOP users.
**Purpose:** Legal compliance and transparency about personal data.
**Contents:** What data is collected and why; who it is shared with (organisation members, carriers); how long it is kept; user rights; acceptable use; the terms of accepting a quote.

### 31. Handover and Maintenance Guide
**Definition:** A consolidated guide for the team that maintains the system after launch.
**Purpose:** Knowledge carries over when people change.
**Contents:** System overview with links to the TAD, BSD, API and run books; access and credentials handover process; scheduled maintenance tasks (updates, certificates, restore tests); known issues and roadmap.

### 32. Project Close-out and Lessons Learned
**Definition:** A final report comparing the results with the PRD goals.
**Purpose:** Formally closes the project and records lessons for future projects.
**Contents:** Success metrics actually achieved; scope delivered versus planned; budget and timeline; what went well and what didn't; recommendations.
