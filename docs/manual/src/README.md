# CIMH Stores Platform v2: System Manual

The written manual for the CIMH Stores Platform: **SHOP** (customer store), **SIA** (staff inventory app) and **SIA Mobile** (Android). It brings together, in one readable place, the details and diagrams from the technical documents ([PRD](../PRD.md), [TRD](../TRD.md), [TAD](../TAD.md), [BSD](../BSD.md), [API](../api/README.md), [APD](../APD.md), [Design Brief](../DESIGN_BRIEF.md), [Security](../SECURITY.md), [Migration](../MIGRATION_PLAN.md), [Infrastructure](../INFRASTRUCTURE.md), [Test Strategy](../TEST_STRATEGY.md), [Implementation Plan](../IMPLEMENTATION_PLAN.md)). Where the manual and a source document disagree, **the source document wins**: please fix the manual.

**Audience:** developers, DevOps, testers, product owner and new team members.

## Contents

| # | Chapter | What it covers |
|---|---|---|
| 1 | [Introduction](01-introduction.md) | What the platform does, goals, scope, key numbers |
| 2 | [Users, roles and apps](02-users-roles-apps.md) | Roles and permissions; SHOP, SIA and Mobile features and navigation maps |
| 3 | [Architecture](03-architecture.md) | System context, containers, services, HTTP calls, Kafka, outbox |
| 4 | [Data](04-data.md) | Where data lives, ownership and access, every collection, relationships, consistency, retention, migration |
| 5 | [Workflows](05-workflows.md) | Registration, paid and Pro Bono requests, quotes, reservations, stow/pick, downloads |
| 6 | [Security](06-security.md) | Login and tokens, authorisation, controls, **threat model** (assets, actors, trust boundaries, STRIDE threats T-01–T-41, secrets, privacy, testing, residual risks) |
| 7 | [Deployment and operations](07-deployment-operations.md) | Machines, Compose, networks, monitoring, releases, backups, transition |
| 8 | [Technology stack](08-technology-stack.md) | Every tool and framework used, and why |
| 9 | [Documentation map and glossary](09-documentation-glossary.md) | How the documents relate; terms |
| 10 | [API](10-api.md) | Base paths, conventions, auth per client, request state machine as endpoints, error codes |
| 11 | [App flows](11-app-flows.md) | Every screen in SHOP, SIA and Mobile, guards, error states, user journeys (J-01–J-11), email deep links |
| 12 | [Design system](12-design-system.md) | Brand, colour tokens (light/dark, contrast-checked), type, spacing, components, screen look, Vuetify/Material theme |
| 13 | [Data migration](13-data-migration.md) | Source inventory, mapping per collection (M01–M09), verification, dry runs, cut-over runbook, rollback |
| 14 | [Infrastructure and environments](14-infrastructure.md) | Machines, VLAN, firewall, Compose services and limits, MongoDB/Kafka/Redis/nginx/ClamAV config, secrets, backups, environments, provisioning, DR |
| 15 | [Testing](15-testing.md) | Test levels, critical cases, authz/IDOR generation, k6 performance, resilience, environments, CI gates, severity, release criteria, traceability |
| 16 | [Implementation plan](16-implementation-plan.md) | Phases P0–P10 with deliverables and exit criteria, Gantt timeline, milestones, doc schedule, roles, risks, scope control |

## Diagram index

All diagrams are drawn with **draw.io**. Sources are in [`diagrams/`](diagrams/) (`.drawio`), exported images in [`images/`](images/) (`.svg`).

| # | Diagram | Used in |
|---|---|---|
| 01 | System context | Ch. 3 |
| 02 | Container view | Ch. 3 |
| 03 | Synchronous HTTP calls between services | Ch. 3 |
| 04 | Kafka topics | Ch. 3 |
| 05 | Outbox relay | Ch. 3 |
| 06 | Deployment (host + 2 Pis) | Ch. 7, 14 |
| 07 | Networks and firewall | Ch. 7, 14 |
| 08 | Data ownership | Ch. 4 |
| 09 | Entity relationships | Ch. 4 |
| 10 | Account status flow | Ch. 5 |
| 11 | Paid request status flow | Ch. 5 |
| 12 | Pro Bono request status flow | Ch. 5 |
| 13 | Registration and approval | Ch. 5 |
| 14 | Paid request: quote to delivery | Ch. 5 |
| 15 | Stock reservation | Ch. 5 |
| 16 | Stow and pick | Ch. 5 |
| 17 | Protected file download | Ch. 5 |
| 18 | Login, refresh and revocation | Ch. 6 |
| 19 | SHOP navigation map | Ch. 2 |
| 20 | SIA navigation map | Ch. 2 |
| 21 | SIA Mobile navigation map | Ch. 2 |
| 22 | Legacy → v2 data cut-over | Ch. 7, 13 |
| 23 | Documentation map | Ch. 9 |
| 24 | Journey: registration and approval | Ch. 11 |
| 25 | Journey: cart → quote → signed agreement | Ch. 11 |
| 26 | Journey: staff request desk | Ch. 11 |
| 27 | Journey: mobile scanning | Ch. 11 |
| 28 | Design tokens (exact colours) | Ch. 12 |
| 29 | Trust boundaries | Ch. 6 |
| 30 | Test levels and CI gates | Ch. 15 |
| 31 | Implementation timeline (Gantt) | Ch. 16 |

## Updating this manual

The manual must be updated whenever a source document (PRD, TRD, TAD, BSD, …) is created or changed. Edit the matching chapter in `docs/manual/src/`, then rebuild:

```powershell
cd docs\manual
pip install markdown   # once
python build.py
```

## Editing diagrams

**Option A: edit in draw.io (best for one-off changes).**
Open the `.drawio` file in draw.io (desktop app installed at `C:\Program Files\draw.io\draw.io.exe`), edit, save, then re-export the SVG:

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f svg --svg-theme dark -o "images\14-paid-request-flow.svg" "diagrams\14-paid-request-flow.drawio"
```

> If you hand-edit a diagram, **don't re-run the generator for that file**, or your edits will be overwritten. Either move the change into `_generate.py`, or remove that diagram from the script.

**Option B: regenerate everything from the script (best for consistent bulk changes).**

```powershell
cd docs\manual\diagrams
python _generate.py
Get-ChildItem *.drawio | ForEach-Object {
  & "C:\Program Files\draw.io\draw.io.exe" -x -f svg --svg-theme dark -o "..\images\$($_.BaseName).svg" $_.FullName
}
```

**Colour key used in every diagram:**

| Colour | Meaning |
|---|---|
| Blue | Client apps / normal states |
| Purple | Edge (nginx) |
| Green | Application services / successful end states |
| Yellow | Workers, relays, notes |
| Orange | Platform components (Kafka, Redis, files, monitoring) |
| Red | MongoDB / failure or cancelled states |

Exports use draw.io's **dark theme** (`--svg-theme dark`); diagram cards in this page are `#121212`. **Exception: `28-design-tokens`** is exported with `--svg-theme light`, because the dark theme recolours its swatches (it draws its own dark background).
| Grey | External systems |
