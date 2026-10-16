"""Serialized application schema initialization and configuration checks."""
import logging
import os

from core.db import get_db_context

logger = logging.getLogger(__name__)
_MIGRATION_LOCK_ID = 684_271_904


def validate_runtime_configuration() -> None:
    insecure = []
    if os.environ.get("JWT_SECRET_KEY", "").lower() in {"", "change_this_secret_in_production", "promptsrc_secret_key_change_in_production_2024"}:
        insecure.append("JWT_SECRET_KEY")
    if os.environ.get("ADMIN_PASSWORD", "") in {"", "admin123", "change_me_in_production"}:
        insecure.append("ADMIN_PASSWORD")
    if os.environ.get("POSTGRES_PASSWORD", "") in {"postgres", ""}:
        insecure.append("POSTGRES_PASSWORD")
    if not os.environ.get("DATA_ENCRYPTION_KEY"):
        source = ("JWT_SECRET_KEY" if os.environ.get("JWT_SECRET_KEY")
                  else "a hardcoded development fallback literal")
        message = (
            f"DATA_ENCRYPTION_KEY is unset: stored credentials (enc:v1:) are being encrypted "
            f"with {source}. Rotating that secret will permanently orphan every stored "
            f"credential — distillation, search and all provider calls then fail with "
            f"'Stored credential cannot be decrypted'. Set an explicit DATA_ENCRYPTION_KEY "
            f"(it must never rotate with auth secrets) and re-enter credentials via the admin UI."
        )
        if os.environ.get("STRICT_STARTUP_VALIDATION", "false").lower() in {"1", "true", "yes"}:
            raise RuntimeError(message)
        logger.warning(message)
    if insecure:
        message = f"Insecure or missing runtime settings: {', '.join(insecure)}"
        if os.environ.get("STRICT_STARTUP_VALIDATION", "false").lower() in {"1", "true", "yes"}:
            raise RuntimeError(message)
        logger.warning(message)


def _validate_credential_envelopes() -> None:
    """Split the envelope gate by recoverability (TASK-257, 2026-10-15 outage).

    Runs ALWAYS once envelopes exist — silent credential orphaning is a
    data-loss event, not a preference gated behind STRICT_STARTUP_VALIDATION.
    Fresh installs (nothing stored yet, or schema still initializing) pass.

      rewrap-able (decrypts under a fallback chain source, or under a fallback
      PRIMARY because DATA_ENCRYPTION_KEY was never promoted) → REFUSE boot:
      these are recoverable, and the recovery (rewrap) must happen BEFORE the
      next key promotion — letting boot proceed is how routine rotations
      silently destroy credentials.

      true orphans (decrypt under no chain source) → WARN and continue:
      unrecoverable ciphertext has nothing left to protect; stranding the
      whole service over it caused the 2026-10-15 outage. An alert row names
      the affected stores so re-entry via the admin UI is loud, not silent.
    """
    from core.secrets import envelope_classification, envelopes_exist, key_source

    if not envelopes_exist():
        return
    classification = envelope_classification()
    if classification["total"] == 0:
        return

    # Envelopes whose only decryptable source is a fallback PRIMARY count as
    # rewrap-able too: promoting the dedicated key + rewrapping is exactly the
    # endpoint's documented flow, and any later fallback rotation orphans them.
    on_dedicated_key = key_source() == "data_key"
    must_rewrap = classification["rewrap_able"] + (
        0 if on_dedicated_key else classification["current"]
    )
    orphans = classification["orphaned"]

    if must_rewrap == 0 and orphans == 0:
        return
    if must_rewrap:
        raise RuntimeError(
            "Stored credential envelopes are not rotation-safe: "
            f"{must_rewrap} of {classification['total']} envelope(s) decrypt only under a "
            f"fallback key source (current DATA_ENCRYPTION_KEY source: "
            f"{classification['current_source']}). Rotating JWT_SECRET_KEY — or promoting a new "
            "DATA_ENCRYPTION_KEY — would permanently orphan them. Rewrap BEFORE promoting the "
            "next key: run `python scripts/remediate_credentials.py rewrap --apply` inside the "
            "container (offline), or POST /api/memory/admin/rewrap-credentials with "
            "DATA_ENCRYPTION_KEY_NEXT set."
        )
    # Orphans only: quarantine is a post-boot remediation (the CLI), never a
    # reason to keep the service down.
    logger.error(
        "Credential orphan alert: %d of %d stored envelope(s) decrypt under NO key source "
        "(per-store: %s). Re-enter affected credentials via the admin UI; recoverable rows can be "
        "quarantined + NULLed with `python scripts/remediate_credentials.py quarantine --apply`.",
        orphans, classification["total"],
        {label: store["orphaned"] for label, store in classification["stores"].items()},
    )
    _alert_credential_orphans(classification)


def _alert_credential_orphans(classification: dict) -> None:
    """Raise a memory_system_alerts row for orphaned envelopes (counts only).

    Best-effort: an alert-insert failure must never block boot."""
    stores_brief = "; ".join(
        f"{label}: {store['orphaned']}/{store['total']} orphaned"
        for label, store in classification["stores"].items()
        if store["orphaned"]
    ) or "none"
    try:
        from core.db import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor()
            # code is memory_system_alerts' PRIMARY KEY — upsert, never insert.
            cursor.execute(
                """
                INSERT INTO memory_system_alerts
                    (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, TRUE, NOW(), NOW())
                ON CONFLICT (code) DO UPDATE SET
                    severity = EXCLUDED.severity,
                    title = EXCLUDED.title,
                    message = EXCLUDED.message,
                    source = EXCLUDED.source,
                    detail = EXCLUDED.detail,
                    active = TRUE,
                    last_seen_at = NOW()
                """,
                (
                    "CREDENTIAL_ORPHANS",
                    "error",
                    "Orphaned credential envelopes",
                    f"{classification['orphaned']} of {classification['total']} stored credential "
                    f"envelope(s) cannot be decrypted under any key source ({stores_brief}). "
                    "Re-enter affected credentials via the admin UI.",
                    "startup_gate",
                    f'{{"orphaned": {classification["orphaned"]}, '
                    f'"total": {classification["total"]}, '
                    f'"current_source": "{classification["current_source"]}"}}',
                ),
            )
    except Exception as exc:
        logger.warning(f"Credential-orphan alert upsert failed (boot continues): {exc}")


def initialize_application() -> None:
    """Run idempotent schema work under a cross-process PostgreSQL lock."""
    from db_init import init_db, seed_admin_user
    from memory_system.store.db import init_memory_db

    validate_runtime_configuration()
    with get_db_context() as lock_conn:
        cursor = lock_conn.cursor()
        cursor.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_ID,))
        try:
            init_db()
            init_memory_db()
            seed_admin_user()
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_ID,))
    _validate_credential_envelopes()
