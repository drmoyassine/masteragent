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
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import hashlib
import psycopg2
from fastapi import Header, HTTPException, Security
from fastapi.security import APIKeyHeader
from jose import jwt, JWTError
from psycopg2.pool import PoolError

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

_MCP_SERVICE_KEY: str = os.environ.get("MCP_SERVICE_KEY", "")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


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


def verify_jwt_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token.
    Returns the full payload dict on success, None on any failure.
    (TASK-259 item 7: callers need the tver claim, not just sub.)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") is None:
            logger.warning("JWT payload missing 'sub' claim")
            return None
        return payload
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


def _token_version_valid(payload: dict, user: dict) -> bool:
    """TASK-259 item 7: the token's tver claim must equal the row's
    token_version. A token WITHOUT tver is invalid — issuing stopped at this
    deploy, so any still-circulating legacy token is treated as revoked
    (clean-slate session revocation). Bumping users.token_version invalidates
    every outstanding token for that user at once."""
    claimed = payload.get("tver")
    if claimed is None:
        return False
    try:
        claimed_v = int(claimed)
    except (TypeError, ValueError):
        return False
    current_v = int(user.get("token_version") or 0)
    return claimed_v == current_v


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
        payload = verify_jwt_token(parts[1])
        if not payload:
            return None
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = %s", (payload["sub"],))
            user = cursor.fetchone()
            if not user:
                return None
            user = dict(user)
            # TASK-259 item 7: version check AFTER the row read (revocation
            # takes effect on the next request after a bump, same as demotion).
            if not _token_version_valid(payload, user):
                logger.warning("JWT tver mismatch/missing for user %s", user.get("id"))
                return None
            return user
    except (PoolError, psycopg2.Error) as e:
        logger.error(f"Authentication database temporarily unavailable: {e}")
        raise HTTPException(status_code=503, detail="Authentication database temporarily unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_user: {e}")
    return None


def require_auth(authorization: str = Header(None)) -> dict:
    """
    Strict authentication dependency — raises HTTP 401 if user is not authenticated.
    Use as: user: dict = Depends(require_auth)

    TASK-259: MCP_SERVICE_KEY authenticates here ONLY as the mcp-service
    identity (the prompts-MCP executor sends it as Bearer) — deliberately
    WITHOUT is_admin. Admin routes require a real human JWT; the service key
    must never reach them (one leaked env var must not be full admin).
    """
    if _MCP_SERVICE_KEY and authorization == f"Bearer {_MCP_SERVICE_KEY}":
        return {"id": "mcp-service", "username": "mcp-service", "is_admin": False}
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin_auth(authorization: str = Header(None)) -> dict:
    """Require an authenticated HUMAN administrator.

    No service-key path: MCP_SERVICE_KEY authenticates as the mcp-service
    identity without is_admin (TASK-259 demotion), so it is refused here.
    Admin users are re-read from the database on every request, so demotion
    takes effect immediately.
    """
    user = require_auth(authorization)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


async def verify_api_key(api_key: str = Security(_api_key_header)) -> Optional[dict]:
    """
    Optional API key authentication dependency (checks api_keys table).
    Returns the key row dict if valid, None otherwise.
    """
    if not api_key:
        return None

    if _MCP_SERVICE_KEY and api_key == _MCP_SERVICE_KEY:
        return {"id": "mcp-service", "user_id": None, "is_service": True}

    # Hash incoming key for comparison
    hashed_key = hash_api_key(api_key)

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_keys WHERE key_hash = %s", (hashed_key,))
        key_row = cursor.fetchone()
        if key_row:
            cursor.execute(
                "UPDATE api_keys SET last_used = %s WHERE id = %s",
                (datetime.now(timezone.utc).isoformat(), key_row["id"]),
            )
            return dict(key_row)
    return None


async def require_api_key(api_key: str = Security(_api_key_header)) -> dict:
    """Strict form of :func:`verify_api_key` for external prompt consumers."""
    key = await verify_api_key(api_key)
    if not key:
        raise HTTPException(status_code=401, detail="Valid API key required")
    return key
