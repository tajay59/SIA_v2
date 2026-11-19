# ADR-0002: FastAPI and Python for all services

- Status: Accepted (2026-11-06)
- Related: TRD (stack and versions), ADR-0001

## Context
The legacy back end is Python (Flask) and the team is one developer who knows Python. The services need async I/O (MongoDB, Kafka, Redis, HTTP between services), OpenAPI contracts, strict request validation and good test tooling.

## Options
1. **FastAPI + Python (latest)**: async, Pydantic validation, OpenAPI out of the box, same language as the legacy code and the migration scripts.
2. **Node.js (NestJS/Fastify)**: same language as the frontends; weaker fit for the image and PDF work and for the existing Python know-how.
3. **Go or Kotlin**: faster per core; a second language to learn and maintain for one developer.

## Decision
Option 1 for every service, the media-worker and the relays. Shared code lives in `packages/py-common`.

## Consequences
- One toolchain (ruff, mypy, pytest, Schemathesis) across all services; contract tests compare each service with `docs/api/`.
- Request bodies are strict (no type coercion), set once in py-common.
- CPU-heavy work stays off the event loop: Argon2 runs in a bounded thread pool (P9 found it blocking logins under a burst), PDF and label rendering in threads.
- Per-core throughput is lower than Go; the measured target is met by running more replicas (ADR-0013).
