# MasterAgent restore runbook (TASK-260)

The memory corpus (postgres `memory` database — raw interactions, memories,
intelligence, knowledge, config) is the state this whole pipeline exists to
produce. Everything else is reconstructable:

| Component | Backed up? | Recovery |
|---|---|---|
| postgres `memory` DB | **Yes** — `pg_dump -Fc` sidecar | this runbook |
| redis (BullMQ queue state) | No (by design) | reconstructable — pending jobs re-fire from the scheduler/claim ledger |
| app volumes (`promptsrc_*`) | No (documented limitation) | app config tables live in postgres; local file caches are disposable |
| gliner cache | No | re-downloaded on next start |

## What exists where

- **Sidecar**: compose service `db_backup` (same `pgvector/pgvector:pg16` image,
  so `pg_dump`/`pg_restore` versions always match the server). Script:
  `deploy/backup.sh`, mounted read-only into the container.
- **Dump target**: host bind mount, default `/var/backups/masteragent`
  (override with `MASTERAGENT_BACKUP_DIR` in the deployment env). Layout:
  - `daily/memory_YYYYMMDD_HHMMSS.dump` — kept 14
  - `weekly/memory_GGGG-Www.dump` — kept 4 (copy of each Sunday's daily)
  - `monthly/memory_YYYYMM.dump` — kept 3 (copy of each 1st's daily)
  - `LAST_RUN.txt` — status of the most recent attempt
  - `FAILED.flag` — written only when a dump fails (removed on success)
- **Schedule**: 02:00 UTC daily; catch-up dump if the container starts after
  02:00 with no dump for that day yet. On the 1st of each month, the latest
  dump is additionally restored into a scratch database `backup_verify` and
  sanity-checked (>= 40 public tables, `memory_settings` row present,
  `interactions` non-empty) before being dropped. Failure of either the dump
  or the check INSERTs a `memory_system_alerts` row (`backup_failed` /
  `backup_restore_check_failed`) which `services/alert_delivery.py` forwards
  to the owner webhook; a passing monthly check posts the expiring
  `backup_restore_check_ok` heartbeat.

## Security note

Dumps are **unencrypted** on the deployment host's own filesystem
(single-operator host; the target was owner-named). If the target ever moves
to shared or off-host storage, encrypt first (`age -r <recipient> out.dump.age`
or `openssl enc`) with a key the owner holds offline — never a key born in
chat. Verify the `MASTERAGENT_BACKUP_DIR` path is not web-served or shared.

## 1. Verify backups are flowing

```sh
# on the host
ls -lh /var/backups/masteragent/daily/ | tail
cat /var/backups/masteragent/LAST_RUN.txt
test -f /var/backups/masteragent/FAILED.flag && echo "LAST RUN FAILED"

# inside the db_backup container (EasyPanel: exec on the db_backup service)
tail -n 40 /proc/1/fd/1 2>/dev/null || docker logs <db_backup container>
```

## 2. Manual run-now dump (post-deploy rehearsal / ad hoc)

```sh
# exec into the db_backup container, then:
/backup.sh once                       # dump only
BACKUP_RESTORE_CHECK=1 /backup.sh once   # dump + restore sanity check
```

## 3. Rehearsed restore into a scratch database (the monthly check, by hand)

```sh
# exec into the db_backup container:
LATEST=$(ls -1t /backups/daily/*.dump | head -n 1)
psql -c "DROP DATABASE IF EXISTS restore_test"
psql -c "CREATE DATABASE restore_test"
pg_restore -d restore_test --no-owner --no-privileges "$LATEST"

# sanity (must reproduce the expected set and non-empty corpus):
psql -d restore_test -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"   # >= 40
psql -d restore_test -Atc "SELECT count(*) FROM memory_settings WHERE id=1"                              # 1
psql -d restore_test -Atc "SELECT count(*) FROM interactions"                                            # > 0

# clean up:
psql -c "DROP DATABASE IF EXISTS restore_test"
```

Acceptance (TASK-260): the restore reproduces the expected table set and
non-empty counts. The implementing agent rehearsed this path after deploy;
the owner signs off.

## 4. Disaster recovery — restore into production

1. **Stop writes**: stop the `masteragent` app service (EasyPanel panel or
   `docker compose stop masteragent`). The scheduler/queue must not write
   while you restore.
2. **Pick the dump**: newest intact `daily/*.dump` (check `LAST_RUN.txt`),
   or the latest weekly/monthly if the daily set is suspect.
3. **Recreate the database** (exec into the `postgres` container as root,
   then `su postgres` — peer auth):

   ```sh
   psql -c "DROP DATABASE IF EXISTS memory"
   psql -c "CREATE DATABASE memory OWNER postgres"
   ```

4. **Restore** (from the postgres container; copy the dump in first —
   `docker cp /var/backups/masteragent/daily/<file>.dump <pg container>:/tmp/`):

   ```sh
   pg_restore -U postgres -d memory --no-owner --no-privileges /tmp/<file>.dump
   ```

   The migration ledger (`schema_migrations`) is part of the dump, so the
   app boots against the restored schema without re-running migrations.
5. **Verify** before re-enabling traffic:

   ```sh
   psql -d memory -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
   psql -d memory -Atc "SELECT version FROM schema_migrations ORDER BY version"
   psql -d memory -Atc "SELECT count(*) FROM memory_settings WHERE id=1"
   ```

6. **Restart** the `masteragent` app service; check `GET /api/health`
   returns and the background loop ticks (scheduler_last_tick in health).
7. **Post-incident**: note the loss window (last good dump → failure) in
   `log.md`; if the dump target or schedule contributed, fix the root cause
   — no band-aids.
