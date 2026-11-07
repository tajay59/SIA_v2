"""Shared building blocks for CIMH Stores v2 services.

Modules:
    errors    RFC 9457 problem responses and stable error codes (API README §4)
    ids       ULID and prefixed id generation
    auth      EdDSA JWT verification against identity's JWKS + Redis revocation
    authz     FastAPI dependencies for roles, ownership and CIMH restrictions
    outbox    Outbox event model, write helper and relay loop (TAD §5)
    consumer  Idempotent Kafka consumer with retry/DLQ routing (TAD §5)
    logging   JSON structured logging with trace ids
    metrics   Prometheus metrics middleware and /metrics endpoint
    app       create_app(): a FastAPI app with all of the above wired in
"""

__version__ = "0.1.0"
