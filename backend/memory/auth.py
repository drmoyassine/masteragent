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
from memory_db import get_memory_db_context

logger = logging.getLogger(__name__)


async def require_admin_auth(authorization: str = Header(None)) -> dict:
    """Require JWT authentication for admin config endpoints.
    Uses core.auth.verify_jwt_token and core.db.get_db_context.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")

        user_id = verify_jwt_token(parts[1])
        if not user_id:
            logger.warning("Memory system auth failed: Invalid or expired token")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            return dict(user)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")


async def verify_agent_key(x_api_key: str = Header(None, alias="X-API-Key")) -> dict:
    """Verify agent API key and return agent info"""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM memory_agents WHERE api_key_hash = ? AND is_active = 1",
            (x_api_key,)
        )
        agent = cursor.fetchone()
        
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Update last used
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("UPDATE memory_agents SET last_used = ? WHERE id = ?", (now, agent["id"]))
        
        return dict(agent)


def log_audit(agent_id: str, action: str, resource_type: str = None, resource_id: str = None, details: dict = None):
    """Log agent activity"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_audit_log (id, agent_id, action, resource_type, resource_id, details_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            agent_id,
            action,
            resource_type,
            resource_id,
            json.dumps(details or {}),
            datetime.now(timezone.utc).isoformat()
        ))
