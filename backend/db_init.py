"""
db_init.py — Database initialization and seeding (PostgreSQL)

Contains: init_db(), seed_admin_user(), and the default template seed data.
All tables now live in the PostgreSQL 'memory' database alongside the memory system.
"""
import uuid
import logging
from datetime import datetime, timezone

from core.auth import hash_password
from core.db import get_db_context
from core.secrets import encrypt_secret, is_encrypted

logger = logging.getLogger(__name__)

def init_db():
    """Create the app tables that survive the §3 freeze; idempotent migrations.

    TASK-257 §3 phase 2: this no longer provisions the prompt-console
    tables (settings, prompts, prompt_versions, prompt_variables, pm_files,
    account_variables, api_keys, templates) — schema is owned by
    backend/migrations/*.sql, and boot DDL outside the ledger is how the
    fossils formed. Their existing rows stay on legacy deployments until the
    prompt-console routes themselves retire (§3 follow-up).
    """
    with get_db_context() as conn:
        cursor = conn.cursor()

        # Pin the database default timezone: the entity-day key is
        # DATE(timestamp), which is session-TZ dependent. Compose pins TZ/PGTZ
        # for the app's own connections; this covers every other client.
        try:
            cursor.execute("""
                DO $$ BEGIN
                    EXECUTE format('ALTER DATABASE %I SET timezone TO %L', current_database(), 'UTC');
                END $$;
            """)
        except Exception as exc:
            logger.warning("Could not pin database timezone to UTC: %s", exc)

        # Users table (live auth surface — admin login)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                github_id BIGINT UNIQUE,
                username TEXT NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT,
                avatar_url TEXT,
                github_url TEXT,
                github_token TEXT,
                plan TEXT DEFAULT 'free',
                is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE")

        # Encrypt credentials written by older releases. This is idempotent and
        # uses the same compatibility envelope as all new credential writes.
        cursor.execute("SELECT id, github_token FROM users WHERE github_token IS NOT NULL AND github_token <> ''")
        for row in cursor.fetchall():
            if not is_encrypted(row["github_token"]):
                cursor.execute(
                    "UPDATE users SET github_token = %s WHERE id = %s",
                    (encrypt_secret(row["github_token"]), row["id"]),
                )

def seed_admin_user():
    """
    Create a default admin user if one doesn't already exist.
    Credentials can be overridden via ADMIN_EMAIL / ADMIN_PASSWORD env vars.
    """
    import os

    if "ADMIN_PASSWORD" not in os.environ:
        logger.warning("Using default admin credentials (admin123). Please set ADMIN_PASSWORD in your .env file!")

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@promptsrc.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, is_admin FROM users WHERE email = %s", (admin_email,))
        existing = cursor.fetchone()
        if not existing:
            now = datetime.now(timezone.utc).isoformat()
            admin_id = str(uuid.uuid4())
            password_hash = hash_password(admin_password)
            cursor.execute(
                """INSERT INTO users (id, username, email, password_hash, plan, is_admin, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, 'pro', TRUE, %s, %s)""",
                (admin_id, admin_username, admin_email, password_hash, now, now),
            )
            logger.info(f"Admin user created: {admin_email}")
        elif not existing.get("is_admin"):
            cursor.execute("UPDATE users SET is_admin = TRUE WHERE id = %s", (existing["id"],))
            logger.info("Promoted configured administrator account: %s", admin_email)
