# Incident response plan and post-mortem template (#25)

For: the on-duty developer/admin when something is broken or a security event is suspected. Severities: TEST_STRATEGY §10. Privacy duties: SECURITY §10 (Barbados Data Protection Act 2019).

## 1. Recognise and classify (first 15 minutes)

| Level | Examples | Response |
|---|---|---|
| **SEV1** | Platform down; data loss or corruption; suspected breach or personal data exposure | Start now, any hour; tell the CIMH IT lead and the business owner |
| **SEV2** | A core journey broken (cannot submit, accept, scan) with no workaround | Same working day |
| **SEV3** | Degraded or partly broken, workaround exists | Next working day |

Write a running log from the start (time, what was seen, what was done): it becomes the post-mortem.

## 2. Contain

- **Service fault:** roll back the last deploy (DEPLOYMENT §Rollback) before debugging.
- **Data being damaged:** stop the writing service(s) (`$C stop <service>`); keep Mongo up for evidence.
- **Suspected account compromise:** suspend the account (A-17; revokes every session at once), reset its password, check the audit log (A-20) for what it did.
- **Leaked secret:** rotate it now (OPERATIONS §Secrets); a leaked JWT key → rotate and restart identity (all tokens die within 15 min).
- **Active attack:** block the source IP in nginx (`deny <ip>;` in the template, `test-config.sh`, reload) or at the CIMH firewall; the auth rate limits already slow guessing.

## 3. Investigate

- `X-Trace-Id` from the user's error → `$C logs <service> | grep <traceId>` across services.
- Audit log (A-20 or `auditlog` collection): who changed what, when, from which IP.
- Prometheus: when error rate, latency or lag changed; compare with deploy times.
- Keep evidence: copy logs (`$C logs --since 24h > incident-<date>.log`) before restarts rotate them.

## 4. Recover

Restore service (rollback, restart, restore from backup: DISASTER_RECOVERY) and verify with the smoke tests and the affected journey by hand.

## 5. Notify

- **Personal data breach** (Data Protection Act 2019): the data controller (CIMH) informs the Data Protection Commissioner without undue delay, and affected people where the risk is high. Prepare: what data, how many people, when, what was done.
- Users: a short email via the lists in A-19 when they were affected (what happened, what to do, e.g. re-enter orders after a restore).

## 6. Close and learn

Within 5 working days of a SEV1/SEV2, write the post-mortem below (blameless: systems and checks, not people), add tests or alerts that would have caught it, and link it from the CLAUDE.md progress log.

---

## Post-mortem template

```markdown
# Post-mortem: <title> (<date>)

| | |
|---|---|
| Severity | SEV1 / SEV2 / SEV3 |
| Duration | <start> – <end> (<minutes>) |
| Impact | who could not do what; data affected (none / lost / exposed: what, how many) |
| Detected by | alert <name> / user report / other |

## Timeline (UTC-4)
- hh:mm  what happened / what was seen / what was done

## Root cause
What failed, and why the existing checks (tests, alerts, review) did not stop it.

## What went well / what went badly

## Actions
| Action | Type (fix / test / alert / doc) | Owner | Due |
|---|---|---|---|
```
