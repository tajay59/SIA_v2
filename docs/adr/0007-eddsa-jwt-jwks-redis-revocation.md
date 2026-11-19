# ADR-0007: EdDSA tokens verified locally via JWKS; revocation in Redis

- Status: Accepted (2026-11-06)
- Related: TAD §8.1, SECURITY, API README §3

## Context
Every service must know who is calling without asking identity-svc on every request, and suspending an account must take effect at once. The legacy app used shared-secret tokens and a SQLite token store.

## Options
1. **Opaque session ids checked with identity on every call**: simple revocation; identity becomes a hot dependency for all traffic.
2. **Shared-secret JWT (HS256)**: any service that can verify a token can also forge one.
3. **Asymmetric JWT (EdDSA) verified from identity's JWKS, with a revocation list in Redis.**

## Decision
Option 3. Access tokens last 15 min; refresh tokens 7 days and are replaced on every use. Tokens carry `sid`; revoked sessions and suspended accounts are checked in Redis, and that check fails closed. Web uses cookies + a CSRF header; mobile uses Bearer. Passwords use Argon2id (m=19 MiB, t=2, p=1). Admins must enrol MFA; until then every endpoint except MFA set-up returns 403 `MFA_REQUIRED`. Service tokens are refused on user endpoints.

## Consequences
- Services verify offline; identity is needed only for login, refresh and JWKS.
- Redis is on the auth path: an outage refuses requests rather than letting revoked tokens through.
- Key rotation = publish the new key in JWKS before signing with it.
- Duplicate cookie names on a shared host are handled by trying each value in browser order (py-common `cookie_values`).
