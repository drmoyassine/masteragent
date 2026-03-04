"""
memory/auth.py — Memory system authentication helpers

Contains:
  - require_admin_auth (JWT user auth mapped from main prompt_manager.db)
  - verify_agent_key (API key auth mapped from memory.db)
  - log_audit (logs agent activity)
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Header, HTTPException

from core.auth import verify_jwt_token
from core.db import get_db_context
from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


async def require_admin_auth(authorization: str = Header(None)) -> dict:
    """Require JWT authentication for admin config endpoints.
    Uses core.auth.verify_jwt_token and core.db.get_db_context.
    """
    if not authorization:
        logger.debug("Memory system auth failed: No authorization header")
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning("Memory system auth failed: Invalid authorization scheme")
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")

        token = parts[1]
        user_id = verify_jwt_token(token)
        if not user_id:
            logger.warning("Memory system auth failed: Invalid or expired token")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                logger.warning(f"Memory system auth failed: User {user_id} not found in database")
                raise HTTPException(status_code=401, detail="User not found")
            return dict(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory system auth failed with unexpected error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


async def verify_agent_key(x_api_key: str = Header(None, alias="X-API-Key")) -> dict:
    """Verify agent API key and return agent info"""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    # Hash the incoming key before comparison (keys stored as SHA-256 hashes)
    import hashlib
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM memory_agents WHERE api_key_hash = %s AND is_active = TRUE",
            (key_hash,)
        )
        agent = cursor.fetchone()

        if not agent:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Update last used timestamp
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE memory_agents SET last_used = %s WHERE id = %s",
            (now, agent["id"])
        )

        return dict(agent)



def log_audit(agent_id: str, action: str, resource_type: str = None, resource_id: str = None, details: dict = None):
    """Log agent activity to the audit log."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_audit_log (id, agent_id, action, resource_type, resource_id, details, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            str(uuid.uuid4()),
            agent_id,
            action,
            resource_type,
            resource_id,
            json.dumps(details or {}),
            datetime.now(timezone.utc).isoformat()
        ))


# Alias: workspace.py and future modules can use either name
require_agent_auth = verify_agent_key
