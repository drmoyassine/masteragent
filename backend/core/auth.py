"""
core/auth.py — Shared authentication utilities

Single source of truth for:
  - JWT SECRET_KEY / ALGORITHM constants
  - hash_password / verify_password
  - create_access_token
  - verify_jwt_token
  - get_current_user  (optional user, returns None if not authenticated)
  - require_auth      (strict user, raises 401 if not authenticated)
  - verify_api_key    (X-API-Key header check against api_keys table)

Previously duplicated across server.py and memory_routes.py.
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import hashlib
from fastapi import Header, HTTPException, Security
from fastapi.security import APIKeyHeader
from jose import jwt, JWTError

from core.db import get_db_context

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

SECRET_KEY: str = os.environ.get(
    "JWT_SECRET_KEY",
    "promptsrc_secret_key_change_in_production_2024",
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ─────────────────────────────────────────────
# Password Hashing
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ─────────────────────────────────────────────
# JWT Utilities
# ─────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """Encode a JWT access token with an expiry."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Created access token for sub: {data.get('sub')}")
    return token


def verify_jwt_token(token: str) -> Optional[str]:
    """
    Decode and validate a JWT token.
    Returns the user_id (sub claim) on success, None on any failure.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            logger.warning("JWT payload missing 'sub' claim")
            return None
        return user_id
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


# ─────────────────────────────────────────────
# FastAPI Dependency Functions
# ─────────────────────────────────────────────

def get_current_user(authorization: str = Header(None)) -> Optional[dict]:
    """
    Optional authentication dependency.
    Parses the Bearer token and returns the user dict, or None if not authenticated.
    Does NOT raise — use require_auth for strict enforcement.
    """
    if not authorization:
        return None
    try:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        user_id = verify_jwt_token(parts[1])
        if not user_id:
            return None
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if user:
                return dict(user)
    except Exception as e:
        logger.error(f"Error in get_current_user: {e}")
    return None


def require_auth(authorization: str = Header(None)) -> dict:
    """
    Strict authentication dependency — raises HTTP 401 if user is not authenticated.
    Use as: user: dict = Depends(require_auth)
    """
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def verify_api_key(api_key: str = Security(_api_key_header)) -> Optional[dict]:
    """
    Optional API key authentication dependency (checks api_keys table).
    Returns the key row dict if valid, None otherwise.
    Note: Currently stores the raw key in key_hash (plaintext comparison).
    Use as: api_key: dict = Depends(verify_api_key)
    """
    if not api_key:
        return None
    
    # Hash incoming key for comparison
    hashed_key = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_keys WHERE key_hash = ?", (hashed_key,))
        key_row = cursor.fetchone()
        if key_row:
            cursor.execute(
                "UPDATE api_keys SET last_used = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), key_row["id"]),
            )
            return dict(key_row)
    return None
