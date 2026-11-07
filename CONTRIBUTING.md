# Contributing (Documentation Index #13)

One developer working with Claude Code. Phases end on exit criteria, not dates.

## Workflow
1. Branch from `main`: `feat/<area>-<short>`, `fix/…`, `chore/…`.
2. Small PRs. Fill in the PR template; link requirement ids (`A3`, `O6`, `TR-AUTH-1`, `T-12`).
3. CI must be green (lint, mypy strict, tests + coverage ≥ 90 % on domain code, authz matrix, scans).
4. Merge to `main` → images built, Trivy-scanned, cosign-signed, deployed to **staging**.
5. Production: run the `deploy-prod` workflow with the digest that passed staging (approval required).

## Rules that CI cannot fully check
- **The contract is `docs/api/`.** Change the spec first, then regenerate clients, event schemas and the matrix.
- **Every endpoint has a row in `tests/authz/matrix.yaml`.** No row, no merge.
- **Hidden data returns 404, not 403** (`ensure_visible`). Only the requester or an admin acts on a request.
- **A service touches only the collections it owns** (CLAUDE.md, BSD §5). Cross-service data goes over Kafka
  or the listed HTTP calls.
- **State change + event in one write** (`outbox_push`). Consumers must be idempotent (`IdempotentConsumer`)
  and apply changes with a conditional update.
- **Status changes follow `tests/transitions/*.yaml`.** Update the table and the domain code together.
- **Money is a 2-decimal string**, stored as Decimal128. Never a float.
- **Never log personal data or secrets.** The JSON formatter redacts common secret keys; don't rely on it.
- **No secrets in git.** Settings go in `deploy/env/*.env`; secrets are Docker secrets in `deploy/secrets/`
  (ignored). Rotate anything that leaks.
- Tag tests with requirement ids (`@pytest.mark.req("O6")`) so the RTM can be generated.

## Style
- Python 3.13, type hints everywhere, `ruff format`, line length 120.
- TypeScript `strict`; Vue 3 `<script setup lang="ts">`; Vuetify via `@cimh/web-ui` only (no ad-hoc colours).
- UI copy in sentence case; plain English (Design Brief §12).

## Commits
Imperative subject (≤ 72 chars), body explains why. Reference requirement ids where relevant.
