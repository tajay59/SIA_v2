# ADR-0006: Outbox stored on the changed document, published by a relay

- Status: Accepted (2026-11-06)
- Related: TAD §5.3, BSD (OutboxEvent), `packages/py-common/src/cimh_common/outbox.py`, ADR-0005

## Context
Saving a change and publishing its event touch two systems. If the service crashes between them, the event is lost, or published for a change that never happened.

## Options
1. **Publish after the write**: loses events on a crash.
2. **Separate `outbox` collection written in a transaction**: correct; one more collection per service and a transaction on every write.
3. **Outbox array on the changed document**, `$push`ed in the same update that changes the entity, published by a relay.

## Decision
Option 3. `outbox_push(event)` adds the event to the same single-document update (atomic without a transaction). One relay per service watches documents with pending events (change stream + 30 s sweep), produces each to Kafka (acks=all), then `$pull`s it.

## Consequences
- No lost events; duplicates are possible, so consumers are idempotent.
- Services export `outbox_*` gauges; alert `OutboxBacklog` fires when a relay falls behind.
- Exception: document-svc owns no collection, so it publishes straight to Kafka and refuses the upload if that fails.
- inventory keeps its outbox on `stock` documents, so stock events are keyed by product id.
