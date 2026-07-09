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
        logger.warning("DATA_ENCRYPTION_KEY is unset; JWT_SECRET_KEY is being used to encrypt stored credentials")
    if insecure:
        message = f"Insecure or missing runtime settings: {', '.join(insecure)}"
        if os.environ.get("STRICT_STARTUP_VALIDATION", "false").lower() in {"1", "true", "yes"}:
            raise RuntimeError(message)
        logger.warning(message)


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
