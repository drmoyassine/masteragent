#!/bin/sh
# TASK-260 — masteragent backup sidecar (pg_dump -Fc + retention + monthly restore check).
#
# Runs in the pgvector/pgvector:pg16 image (pg_dump version exactly matches the
# server). Connectivity via PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE (compose).
#
#   /backup.sh          loop: daily dump at 02:00 UTC, retention prune,
#                       restore sanity check on the 1st (or BACKUP_RESTORE_CHECK=1)
#   /backup.sh once     single dump + exit (manual run-now / post-deploy rehearsal)
#
# Dumps land in $BACKUP_DIR (host bind mount; default /var/backups/masteragent):
#   daily/   memory_YYYYMMDD_HHMMSS.dump   keep 14
#   weekly/  memory_GGGG-Www.dump          keep 4  (copy of Sunday's daily)
#   monthly/ memory_YYYYMM.dump            keep 3  (copy of the 1st's daily)
# LAST_RUN.txt is rewritten on every attempt; a failure also writes FAILED.flag
# and INSERTs a memory_system_alerts row (code backup_failed / backup_restore_check_failed)
# — the in-app alert-delivery poller (services/alert_delivery.py) forwards it to
# the owner channel. If postgres itself is unreachable the alert INSERT cannot
# land either; LAST_RUN.txt + FAILED.flag on the mount are the offline trace.

set -u

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAILY=14
KEEP_WEEKLY=4
KEEP_MONTHLY=3
VERIFY_DB="backup_verify"

log() { echo "[backup $(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }

psql_cmd() { psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 "$@"; }

# record_alert CODE SEVERITY TITLE MESSAGE DETAIL_JSON [EXPIRES_HOURS]
record_alert() {
    expires_sql=""
    if [ "${6:-}" != "" ]; then
        expires_sql=", expires_at=NOW() + ($6 * INTERVAL '1 hour')"
    fi
    psql_cmd -c "
        INSERT INTO memory_system_alerts
            (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
        VALUES ('$1', '$2', '$3', '$4', 'backup', '$5'::jsonb, TRUE, NOW(), NOW())
        ON CONFLICT (code) DO UPDATE SET
            active=TRUE, severity=EXCLUDED.severity, title=EXCLUDED.title,
            message=EXCLUDED.message, detail=EXCLUDED.detail, last_seen_at=NOW()$expires_sql" \
        || log "ALERT: could not record '$1' in DB (postgres unreachable?)"
}

dump_once() {
    ts=$(date -u +%Y%m%d_%H%M%S)
    mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly" "$BACKUP_DIR/monthly"
    target="$BACKUP_DIR/daily/memory_${ts}.dump"
    # Atomic dump: pg_dump writes to a .part file that is renamed only on
    # success — a killed/crashed dump can never leave a partial *.dump behind
    # for the retention prune or the restore check to treat as "latest".
    part="$target.part"
    log "dumping ${PGDATABASE} to $target"
    if ! pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Fc -f "$part"; then
        log "pg_dump FAILED"
        rm -f "$part"
        echo "FAILED $(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$BACKUP_DIR/FAILED.flag"
        echo "STATUS=failed AT=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$BACKUP_DIR/LAST_RUN.txt"
        record_alert backup_failed error "MasterAgent backup failed" \
            "pg_dump failed at ${ts} UTC (see db_backup container logs; /backups/FAILED.flag on the host)" '{}'
        return 1
    fi
    rm -f "$BACKUP_DIR/FAILED.flag"
    mv -f "$part" "$target"
    size=$(du -h "$target" | cut -f1)
    echo "STATUS=ok FILE=$target SIZE=$size" > "$BACKUP_DIR/LAST_RUN.txt"
    log "dump complete ($size)"

    # Retention copies + prune (14 daily / 4 weekly from Sundays / 3 monthly from the 1st).
    if [ "$(date -u +%u)" = "7" ]; then
        cp -f "$target" "$BACKUP_DIR/weekly/memory_$(date -u +%G-W%V).dump"
    fi
    if [ "$(date -u +%d)" = "01" ]; then
        cp -f "$target" "$BACKUP_DIR/monthly/memory_$(date -u +%Y%m).dump"
    fi
    ls -1t "$BACKUP_DIR/daily"/*.dump 2>/dev/null | tail -n +$((KEEP_DAILY + 1)) | xargs -r rm -f
    ls -1t "$BACKUP_DIR/weekly"/*.dump 2>/dev/null | tail -n +$((KEEP_WEEKLY + 1)) | xargs -r rm -f
    ls -1t "$BACKUP_DIR/monthly"/*.dump 2>/dev/null | tail -n +$((KEEP_MONTHLY + 1)) | xargs -r rm -f
    return 0
}

restore_check() {
    latest=$(ls -1t "$BACKUP_DIR/daily"/*.dump 2>/dev/null | head -n 1)
    if [ -z "$latest" ]; then
        log "restore check skipped: no dump found"
        return 1
    fi
    log "restore check: $(basename "$latest") into scratch db $VERIFY_DB"
    psql_cmd -c "DROP DATABASE IF EXISTS $VERIFY_DB" || return 1
    psql_cmd -c "CREATE DATABASE $VERIFY_DB" || return 1
    if ! pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$VERIFY_DB" \
         --no-owner --no-privileges "$latest"; then
        record_alert backup_restore_check_failed error "MasterAgent restore check failed" \
            "pg_restore of $(basename "$latest") into $VERIFY_DB failed" '{}'
        psql_cmd -c "DROP DATABASE IF EXISTS $VERIFY_DB"
        return 1
    fi
    # Sanity: expected table set and a non-empty corpus.
    tables=$(psql_cmd -d "$VERIFY_DB" -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
    settings_rows=$(psql_cmd -d "$VERIFY_DB" -Atc "SELECT count(*) FROM public.memory_settings WHERE id=1")
    interactions=$(psql_cmd -d "$VERIFY_DB" -Atc "SELECT count(*) FROM public.interactions" 2>/dev/null || echo 0)
    psql_cmd -c "DROP DATABASE IF EXISTS $VERIFY_DB"

    ok=0
    [ "${tables:-0}" -ge 40 ] || ok=1
    [ "${settings_rows:-0}" -ge 1 ] || ok=1
    [ "${interactions:-0}" -ge 1 ] || ok=1
    detail="{\"tables\": ${tables:-0}, \"memory_settings_rows\": ${settings_rows:-0}, \"interactions\": ${interactions:-0}}"
    if [ "$ok" -ne 0 ]; then
        record_alert backup_restore_check_failed error "MasterAgent restore sanity check failed" \
            "restored db failed sanity: tables=$tables settings=$settings_rows interactions=$interactions (thresholds: >=40 / >=1 / >=1)" \
            "$detail"
        return 1
    fi
    log "restore check passed (tables=$tables settings=$settings_rows interactions=$interactions)"
    # Heartbeat: proves monthly that the restore path works; expires in 7 days.
    record_alert backup_restore_check_ok warning "MasterAgent monthly restore check passed" \
        "$(basename "$latest") restored: tables=$tables settings_rows=$settings_rows interactions=$interactions" \
        "$detail" 168
    return 0
}

if [ "${1:-}" = "once" ]; then
    dump_once || exit 1
    if [ "${BACKUP_RESTORE_CHECK:-0}" = "1" ]; then
        restore_check || log "restore check failed (alert recorded)"
    fi
    exit 0
fi

log "backup loop starting (daily 02:00 UTC; PGHOST=$PGHOST db=$PGDATABASE; dir=$BACKUP_DIR)"

# Catch-up: started after today's 02:00 with no dump for today yet — take it now.
today_prefix="$BACKUP_DIR/daily/memory_$(date -u +%Y%m%d)_"
ls "${today_prefix}"*.dump >/dev/null 2>&1
if [ $? -ne 0 ]; then
    today_run=$(date -u -d "today 02:00" +%s)
    if [ "$today_run" -le "$(date -u +%s)" ]; then
        log "catch-up: today's 02:00 UTC passed without a dump"
        dump_once
        if [ "$(date -u +%d)" = "01" ]; then
            restore_check || log "restore check failed (alert recorded)"
        fi
    fi
fi

while :; do
    now=$(date -u +%s)
    run_epoch=$(date -u -d "today 02:00" +%s)
    if [ "$run_epoch" -le "$now" ]; then
        run_epoch=$(date -u -d "tomorrow 02:00" +%s)
    fi
    wait_seconds=$((run_epoch - now))
    log "next dump at $(date -u -d "@$run_epoch" '+%Y-%m-%dT%H:%M:%SZ') (sleeping ${wait_seconds}s)"
    sleep "$wait_seconds"
    if dump_once; then
        if [ "$(date -u +%d)" = "01" ] || [ "${BACKUP_RESTORE_CHECK:-0}" = "1" ]; then
            restore_check || log "restore check failed (alert recorded)"
        fi
    fi
done
