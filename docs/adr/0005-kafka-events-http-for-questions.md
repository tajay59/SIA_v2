# ADR-0005: Kafka for events between services; HTTP only for immediate questions

- Status: Accepted (2026-11-06)
- Related: TAD §5.2–§5.3, `docs/api/events.asyncapi.yaml`, ADR-0006

## Context
With services owning their data (ADR-0003), they need to learn about each other's changes (a quote sent → reserve stock → email the customer → render the agreement) without calling each other in chains that fail together.

## Options
1. **HTTP calls only**: simple, but every workflow becomes a chain of calls; one slow service stalls the rest.
2. **Redis streams or RabbitMQ**: lighter; weaker retention, replay and per-key ordering than Kafka.
3. **Kafka (KRaft, 3 brokers) for facts, HTTP for questions that need an answer now.**

## Decision
Option 3. Every state change is an event (envelope `eventId, type, version, occurredAt, correlationId, actorId, payload`; key = entity id, so one entity's events stay in order). Consumers retry through retry topics, then a DLQ. Synchronous HTTP is limited to the calls in TAD §5.2 (e.g. order → inventory availability, document → order access), over the internal network with a service token, 2 s timeout and a circuit breaker.

## Consequences
- Workflows are eventually consistent; screens show interim states (e.g. a line "Reserving…").
- Consumers must be idempotent (processed event ids in Redis), since events can arrive twice (ADR-0006).
- Secrets never travel in Kafka: verification codes are claimed once over HTTP (`/internal/codes/{codeRef}`).
- Three brokers cost about 4.5 GB of the 32 GB budget; they run with SASL/mTLS and per-service ACLs.
- A new consumer group starts at the latest offset and skips events older than 48 h, so old news isn't re-sent.
