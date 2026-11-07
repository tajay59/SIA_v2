## What and why
<!-- One paragraph. Link requirement ids: PRD (A*, C*, O*…), TR-*, threats T-*, journeys J-*. -->

## Checklist
- [ ] Spec in `docs/api/` updated first (if the API or events changed); clients/schemas regenerated
- [ ] New endpoints added to `tests/authz/matrix.yaml`; hidden data returns 404
- [ ] Status changes match `tests/transitions/*.yaml`
- [ ] State change and outbox event saved in one write; consumers idempotent
- [ ] Tests tagged with requirement ids; coverage still ≥ 90 % on domain code
- [ ] No personal data or secrets in code, logs, fixtures or screenshots
- [ ] Docs/CLAUDE.md updated if behaviour or decisions changed

## How I tested it
