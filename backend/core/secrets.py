"""Encryption helpers for credentials persisted by MasterAgent.

Values written by older releases were plaintext.  ``decrypt_secret`` deliberately
accepts those values so deployments can roll forward without a flag day; all new
writes use an authenticated Fernet envelope prefixed with ``enc:v1:``.
"""
import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)
_PREFIX = "enc:v1:"

# Key sources in resolution order — must stay in sync with _fernet().
_SOURCE_ENV_VARS = ("DATA_ENCRYPTION_KEY", "JWT_SECRET_KEY")
_DEV_DEFAULT = "promptsrc_secret_key_change_in_production_2024"


def _fernet_from_source(source: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(source.encode("utf-8")).digest())
    return Fernet(key)


def key_source() -> str:
    """Which source _fernet() currently resolves to."""
    if os.environ.get("DATA_ENCRYPTION_KEY"):
        return "data_key"
    if os.environ.get("JWT_SECRET_KEY"):
        return "jwt_fallback"
    return "dev_default"


def _sources() -> list:
    """All candidate key sources in resolution order.

    DATA_ENCRYPTION_KEY_NEXT (when set) joins the chain so envelopes re-wrapped
    by the rotation endpoint keep decrypting in the running process during the
    promote→restart window. Dev fallback stays last."""
    sources = [os.environ[name] for name in _SOURCE_ENV_VARS if os.environ.get(name)]
    transition = os.environ.get("DATA_ENCRYPTION_KEY_NEXT")
    if transition:
        sources.append(transition)
    sources.append(_DEV_DEFAULT)
    return sources


def _fernet() -> Fernet:
    source = os.environ.get("DATA_ENCRYPTION_KEY") or os.environ.get("JWT_SECRET_KEY")
    if not source:
        # Backward-compatible development fallback. Production startup validation
        # warns loudly about this; keeping the fallback avoids making old local
        # installations unreadable during upgrade.
        source = _DEV_DEFAULT
    return _fernet_from_source(source)


def encrypt_secret(value: Optional[str]) -> Optional[str]:
    """Encrypt a non-empty value, leaving None/empty strings unchanged."""
    if not value or value.startswith(_PREFIX):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_secret(value: Optional[str]) -> Optional[str]:
    """Decrypt an envelope, or return legacy plaintext unchanged."""
    if not value or not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        logger.error("Unable to decrypt stored secret; verify DATA_ENCRYPTION_KEY")
        raise ValueError("Stored credential cannot be decrypted") from exc


def is_encrypted(value: Optional[str]) -> bool:
    return bool(value and value.startswith(_PREFIX))


def _decrypts_under(value: str, fernet: Fernet) -> bool:
    try:
        fernet.decrypt(value[len(_PREFIX):].encode("ascii"))
        return True
    except (InvalidToken, ValueError):
        return False


# Stored credential envelopes live in these columns (value, never selected for
# output — health reporting is counts only).
_ENVELOPE_QUERIES = (
    ("provider_credentials",
     "SELECT api_key_encrypted AS v FROM memory_llm_providers "
     "WHERE api_key_encrypted LIKE 'enc:v1:%'"),
    ("supabase_db_url",
     "SELECT supabase_db_url AS v FROM memory_settings "
     "WHERE supabase_db_url LIKE 'enc:v1:%'"),
    ("webhook_secrets",
     "SELECT secret_encrypted AS v FROM memory_webhook_sources "
     "WHERE secret_encrypted LIKE 'enc:v1:%'"),
)


def envelopes_exist() -> bool:
    """True when at least one stored credential envelope exists.

    False also covers "schema not initialized yet" (fresh first boot) — the
    startup gate then has nothing to validate."""
    try:
        from core.db import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor()
            for _label, query in _ENVELOPE_QUERIES:
                cursor.execute(f"SELECT COUNT(*) AS cnt FROM ({query}) q")
                if (cursor.fetchone()["cnt"] or 0) > 0:
                    return True
        return False
    except Exception as exc:
        logger.warning(f"envelopes_exist check skipped (schema may not be initialized): {exc}")
        return False


def envelope_health() -> dict:
    """Count stored credential envelopes by decryptability under the current
    key-resolution chain. Counts only — secret values never enter the result."""
    from core.db import get_db_context
    fernets = [_fernet_from_source(source) for source in _sources()]
    health = {"total": 0, "decryptable": 0, "orphaned": 0, "current_source": key_source()}
    for label, query in _ENVELOPE_QUERIES:
        try:
            with get_db_context() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()
        except Exception as exc:
            logger.warning(f"envelope_health: {label} scan skipped: {exc}")
            continue
        ok = sum(1 for row in rows if any(_decrypts_under(row["v"], f) for f in fernets))
        health["total"] += len(rows)
        health["decryptable"] += ok
        health["orphaned"] += len(rows) - ok
        health[f"{label}_total"] = len(rows)
    return health


def rotation_safe() -> bool:
    """True when every stored envelope decrypts under the dedicated
    DATA_ENCRYPTION_KEY primary source. False when any envelope only decrypts
    via the JWT/dev fallbacks — a JWT rotation (or setting DATA_ENCRYPTION_KEY
    later) would permanently orphan them. Trivially True with no envelopes."""
    if key_source() != "data_key":
        return False
    health = envelope_health()
    return health["total"] == 0 or health["orphaned"] == 0
