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


def _fernet() -> Fernet:
    source = os.environ.get("DATA_ENCRYPTION_KEY") or os.environ.get("JWT_SECRET_KEY")
    if not source:
        # Backward-compatible development fallback. Production startup validation
        # warns loudly about this; keeping the fallback avoids making old local
        # installations unreadable during upgrade.
        source = "promptsrc_secret_key_change_in_production_2024"
    key = base64.urlsafe_b64encode(hashlib.sha256(source.encode("utf-8")).digest())
    return Fernet(key)


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
