"""Optional per-agent entity authorization.

The feature flag defaults off in Compose for a no-regression rollout. New
installations should enable ENFORCE_AGENT_SCOPE; grants are populated naturally
from ingestion and backfilled from historical interactions.
"""
import os

from fastapi import HTTPException

from core.storage import get_memory_db_context


def scope_enforced() -> bool:
    return os.environ.get("ENFORCE_AGENT_SCOPE", "false").lower() in {"1", "true", "yes"}


def grant_entity(agent_id: str, entity_type: str, entity_id: str) -> None:
    if not agent_id or agent_id == "mcp-service" or not entity_type or not entity_id:
        return
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_agent_entities (agent_id, entity_type, entity_id)
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
        """, (agent_id, entity_type, entity_id))


def ensure_entity_access(agent: dict, entity_type: str, entity_id: str) -> None:
    if not scope_enforced() or agent.get("id") == "mcp-service" or agent.get("access_level") == "shared":
        return
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM memory_agent_entities WHERE agent_id=%s AND entity_type=%s AND entity_id=%s",
            (agent.get("id"), entity_type, entity_id),
        )
        if cursor.fetchone():
            return
        # Preserve the common has-context-before-first-ingest workflow: an entity
        # with no data yet has nothing sensitive to disclose and can be claimed by
        # the first subsequent write.
        cursor.execute("""
            SELECT 1 FROM interactions WHERE primary_entity_type=%s AND primary_entity_id=%s
            UNION ALL SELECT 1 FROM memories WHERE primary_entity_type=%s AND primary_entity_id=%s
            UNION ALL SELECT 1 FROM intelligence WHERE primary_entity_type=%s AND primary_entity_id=%s
            LIMIT 1
        """, (entity_type, entity_id, entity_type, entity_id, entity_type, entity_id))
        if not cursor.fetchone():
            return
        raise HTTPException(status_code=403, detail="Agent is not authorized for this entity")


def ensure_record_access(agent: dict, table: str, record_id: str) -> None:
    if not scope_enforced() or agent.get("id") == "mcp-service" or agent.get("access_level") == "shared":
        return
    if table not in {"interactions", "memories", "intelligence"}:
        raise ValueError("Unsupported scoped table")
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT primary_entity_type, primary_entity_id FROM {table} WHERE id=%s",
            (record_id,),
        )
        row = cursor.fetchone()
    if row:
        ensure_entity_access(agent, row["primary_entity_type"], row["primary_entity_id"])
