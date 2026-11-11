# Legacy → v2 data migration (demo production on staging-lite)

Input: a mongoexport of the legacy `inventory` db in `db/` (git-ignored: real personal data, never commit).

1. `python tools/migrate/legacy_to_v2.py db db/v2`: converts M01–M07 + `stock` (MIGRATION_PLAN §5); writes
   `db/v2/<collection>.json` and `db/v2/report.json` (ids and counts only).
2. Copy `db/v2/*.json` + `load_staging.sh` to `/opt/sia-staging/import/` (mode 600), run
   `bash load_staging.sh /opt/sia-staging/import` on kw-server, then delete the json files. It dumps the
   current db to `/opt/sia-staging/backups/`, stops the apps, replaces the collections, flushes Redis and
   restarts (indexes + `xuser` view are created by the services).
3. Files (M08): with the legacy `app/` folder available locally,
   `python tools/migrate/files_to_v2.py <legacy app dir> db/v2 db/v2-files`, copy `db/v2-files` to the server
   and run `bash load_files_staging.sh <dir>`.
   Product and order ids are stable, so it can run any time after step 2.

Rules applied beyond the plan: duplicate emails keep the account with orders, else the oldest; accounts get
their organisation from their latest order (legacy had no org field); unknown countries default to `BB`.

## DR-1 (local rehearsal, MIGRATION_PLAN §7)
`bash tools/migrate/dr1.sh db` (repo root; Docker + `.venv`): converts, loads into a **throwaway** MongoDB on port
27099 (removed afterwards), runs M09 through the services' own `ensure_indexes`/`ensure_view`, and runs the §6
checks. Output in `db/v2/`: `report.json` (ids, counts, mapping summary), `mappings.local.json` (full free-text
mapping table, may contain names: review locally, never share), `dr1/verify.{json,md}`. Exit code 1 if any check
fails. `dr1.py` refuses any target that is not a localhost port other than 27017/27018, because it wipes it.
