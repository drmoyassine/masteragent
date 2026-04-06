"""
memory/auth.py — Memory system authentication helpers

Contains:
  - require_admin_auth: JWT user auth (alias of core/auth.require_auth)
  - verify_agent_key: API key auth against memory_agents table
  - require_agent_auth: alias of verify_agent_key
  - log_audit: logs agent activity to memory_audit_log
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import Header, HTTPException

# require_admin_auth is identical to require_auth — simply re-exported for clarity
from core.auth import require_auth as require_admin_auth  # noqa: F401
from core.storage import get_memory_db_context
from core.utils import utcnow

logger = logging.getLogger(__name__)


async def verify_agent_key(x_api_key: str = Header(None, alias="X-API-Key")) -> dict:
    """Verify agent API key and return agent info."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

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

        cursor.execute(
            "UPDATE memory_agents SET last_used = %s WHERE id = %s",
            (utcnow(), agent["id"])
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
            utcnow(),
        ))


# Alias: workspace.py and future modules can use either name
require_agent_auth = verify_agent_key
