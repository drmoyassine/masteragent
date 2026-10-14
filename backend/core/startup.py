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
    """Fail closed when stored credentials aren't guaranteed decryptable.

    Runs ALWAYS once envelopes exist — silent credential orphaning is a
    data-loss event, not a preference gated behind STRICT_STARTUP_VALIDATION.
    Fresh installs (nothing stored yet, or schema still initializing) pass."""
    from core.secrets import envelope_health, envelopes_exist, rotation_safe

    if not envelopes_exist():
        return
    if rotation_safe():
        return
    health = envelope_health()
    raise RuntimeError(
        "Stored credential envelopes are not rotation-safe: "
        f"{health['orphaned']} of {health['total']} stored credential envelope(s) cannot be "
        f"guaranteed decryptable (current DATA_ENCRYPTION_KEY source: {health['current_source']}). "
        "Rotating JWT_SECRET_KEY — or setting DATA_ENCRYPTION_KEY later — would permanently orphan "
        "them ('Stored credential cannot be decrypted' on every provider call). Set a dedicated "
        "DATA_ENCRYPTION_KEY and migrate envelopes via POST /api/memory/admin/rewrap-credentials "
        "(DATA_ENCRYPTION_KEY_NEXT transition), or re-enter credentials via the admin UI."
    )


def initialize_application() -> None:
    """Run idempotent schema work under a cross-process PostgreSQL lock."""
    from db_init import init_db, seed_admin_user
    from memory_db import init_memory_db

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
