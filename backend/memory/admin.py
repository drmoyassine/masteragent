"""
memory/admin.py — Admin endpoints for the Memory System

Provides:
  - Insight CRUD (Tier 2): list, get, create, update status, delete
  - Lesson CRUD (Tier 3): list, get, create, update, delete, promote from insight
  - Entity Type Config: get, update per-entity-type compaction/NER settings
  - Manual triggers: compact entity, run memory generation
  - Interactions: list, get individual interaction
  - Audit log: read-only

Auth: Admin JWT (require_admin_auth)
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body

from core.storage import get_memory_db_context
from memory_models import (
    InsightCreate, InsightResponse, InsightUpdate,
    LessonCreate, LessonResponse, LessonUpdate,
    EntityTypeConfig, EntityTypeConfigUpdate,
    InteractionResponse, TimelineEntry,
)
from memory.auth import require_admin_auth

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# INSIGHTS (Tier 2)
# ============================================================

@router.get("/insights")
async def list_insights(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),      # draft | confirmed | archived
    insight_type: Optional[str] = Query(None),
    limit: int = Query(30, le=100),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """List insights with optional filters."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if entity_type:
            conditions.append("primary_entity_type = %s")
            params.append(entity_type)
        if entity_id:
            conditions.append("primary_entity_id = %s")
            params.append(entity_id)
        if status:
            conditions.append("status = %s")
            params.append(status)
        if insight_type:
            conditions.append("insight_type = %s")
            params.append(insight_type)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params_count = list(params)
        cursor.execute(f"SELECT COUNT(*) as total FROM insights {where}", params_count)
        total = cursor.fetchone()["total"]

        params += [limit, offset]
        cursor.execute(f"""
            SELECT id, primary_entity_type, primary_entity_id, source_memory_ids,
                   insight_type, name, content, summary, status,
                   created_by, confirmed_by, confirmed_at, created_at, updated_at
            FROM insights {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params)
        rows = cursor.fetchall()

    return {"insights": [dict(r) for r in rows], "total": total}


@router.get("/insights/{insight_id}")
async def get_insight(insight_id: str, admin: dict = Depends(require_admin_auth)):
    """Get a single insight by ID."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM insights WHERE id = %s", (insight_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Insight not found")
    return dict(row)


@router.post("/insights")
async def create_insight(body: InsightCreate, admin: dict = Depends(require_admin_auth)):
    """Manually create an insight (draft)."""
    insight_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO insights (
                id, primary_entity_type, primary_entity_id, source_memory_ids,
                insight_type, name, content, summary,
                status, created_by, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            insight_id, body.primary_entity_type, body.primary_entity_id,
            body.source_memory_ids or [],
            body.insight_type, body.name, body.content, body.summary,
            "draft", "admin", now, now
        ))

    return {"id": insight_id, "status": "draft", "created_at": now}


@router.patch("/insights/{insight_id}")
async def update_insight(
    insight_id: str,
    body: InsightUpdate,
    admin: dict = Depends(require_admin_auth)
):
    """Update an insight's fields or status (confirm/archive)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status FROM insights WHERE id = %s", (insight_id,))
        existing = cursor.fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="Insight not found")

    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []

    if body.name is not None:
        fields.append("name = %s"); values.append(body.name)
    if body.content is not None:
        fields.append("content = %s"); values.append(body.content)
    if body.summary is not None:
        fields.append("summary = %s"); values.append(body.summary)
    if body.insight_type is not None:
        fields.append("insight_type = %s"); values.append(body.insight_type)
    if body.status is not None:
        fields.append("status = %s"); values.append(body.status)
        if body.status == "confirmed":
            fields.append("confirmed_by = %s"); values.append("admin")
            fields.append("confirmed_at = %s"); values.append(now)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields.append("updated_at = %s"); values.append(now)
    values.append(insight_id)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE insights SET {', '.join(fields)} WHERE id = %s",
            values
        )

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM insights WHERE id = %s", (insight_id,))
        updated = cursor.fetchone()

    return dict(updated) if updated else {"id": insight_id, "updated_at": now}


@router.delete("/insights/{insight_id}", status_code=204)
async def delete_insight(insight_id: str, admin: dict = Depends(require_admin_auth)):
    """Delete an insight."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM insights WHERE id = %s", (insight_id,))


@router.post("/insights/{insight_id}/promote")
async def promote_insight_to_lesson(
    insight_id: str,
    admin: dict = Depends(require_admin_auth)
):
    """Manually promote a confirmed insight to a lesson (async background job)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM insights WHERE id = %s", (insight_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Insight not found")

    # Run promotion in background
    import asyncio
    from memory_tasks import promote_to_lesson
    asyncio.create_task(promote_to_lesson(insight_id))
    return {"message": "Promotion started", "insight_id": insight_id}


# ============================================================
# LESSONS (Tier 3)
# ============================================================

@router.get("/lessons")
async def list_lessons(
    lesson_type: Optional[str] = Query(None),
    visibility: Optional[str] = Query(None),
    limit: int = Query(30, le=100),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """List lessons with optional filters."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if lesson_type:
            conditions.append("lesson_type = %s"); params.append(lesson_type)
        if visibility:
            conditions.append("visibility = %s"); params.append(visibility)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params_count = list(params)
        cursor.execute(f"SELECT COUNT(*) as total FROM lessons {where}", params_count)
        total = cursor.fetchone()["total"]

        params += [limit, offset]
        cursor.execute(f"""
            SELECT id, source_insight_ids, lesson_type, name, content,
                   summary, visibility, tags, created_at, updated_at
            FROM lessons {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params)
        rows = cursor.fetchall()

    return {"lessons": [dict(r) for r in rows], "total": total}


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str, admin: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM lessons WHERE id = %s", (lesson_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return dict(row)


@router.post("/lessons")
async def create_lesson(body: LessonCreate, admin: dict = Depends(require_admin_auth)):
    """Manually create a lesson."""
    lesson_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO lessons (
                id, source_insight_ids, lesson_type, name, content, summary,
                visibility, tags, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            lesson_id, body.source_insight_ids or [],
            body.lesson_type, body.name, body.content, body.summary,
            body.visibility, body.tags or [], now, now
        ))

    return {"id": lesson_id, "created_at": now}


@router.patch("/lessons/{lesson_id}")
async def update_lesson(
    lesson_id: str,
    body: LessonUpdate,
    admin: dict = Depends(require_admin_auth)
):
    """Update a lesson's fields."""
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []

    if body.name is not None:
        fields.append("name = %s"); values.append(body.name)
    if body.content is not None:
        fields.append("content = %s"); values.append(body.content)
    if body.summary is not None:
        fields.append("summary = %s"); values.append(body.summary)
    if body.lesson_type is not None:
        fields.append("lesson_type = %s"); values.append(body.lesson_type)
    if body.visibility is not None:
        fields.append("visibility = %s"); values.append(body.visibility)
    if body.tags is not None:
        fields.append("tags = %s"); values.append(body.tags)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields.append("updated_at = %s"); values.append(now)
    values.append(lesson_id)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE lessons SET {', '.join(fields)} WHERE id = %s",
            values
        )

    return {"id": lesson_id, "updated_at": now}


@router.delete("/lessons/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: str, admin: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM lessons WHERE id = %s", (lesson_id,))


# ============================================================
# ENTITY TYPE CONFIG
# ============================================================

@router.get("/entity-type-config/{entity_type}")
async def get_entity_type_config(entity_type: str, admin: dict = Depends(require_admin_auth)):
    """Get per-entity-type configuration."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM memory_entity_type_config WHERE entity_type = %s",
            (entity_type,)
        )
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Entity type config not found")
    config = dict(row)
    if isinstance(config.get("metadata_field_map"), str):
        config["metadata_field_map"] = json.loads(config["metadata_field_map"])
    return config


@router.patch("/entity-type-config/{entity_type}")
async def update_entity_type_config(
    entity_type: str,
    body: EntityTypeConfigUpdate,
    admin: dict = Depends(require_admin_auth)
):
    """Update per-entity-type configuration."""
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []

    if body.compaction_threshold is not None:
        fields.append("compaction_threshold = %s"); values.append(body.compaction_threshold)
    if body.insight_auto_approve is not None:
        fields.append("insight_auto_approve = %s"); values.append(body.insight_auto_approve)
    if body.lesson_auto_promote is not None:
        fields.append("lesson_auto_promote = %s"); values.append(body.lesson_auto_promote)
    if body.ner_enabled is not None:
        fields.append("ner_enabled = %s"); values.append(body.ner_enabled)
    if body.ner_confidence_threshold is not None:
        fields.append("ner_confidence_threshold = %s"); values.append(body.ner_confidence_threshold)
    # ner_schema and insight_trigger_days are legitimately nullable (None = clear them).
    # Use model_fields_set to detect explicitly-sent null vs not-provided.
    if "ner_schema" in body.model_fields_set:
        fields.append("ner_schema = %s")
        values.append(json.dumps(body.ner_schema) if body.ner_schema is not None else None)
    if "insight_trigger_days" in body.model_fields_set:
        fields.append("insight_trigger_days = %s"); values.append(body.insight_trigger_days)
    if body.embedding_enabled is not None:
        fields.append("embedding_enabled = %s"); values.append(body.embedding_enabled)
    if body.pii_scrub_lessons is not None:
        fields.append("pii_scrub_lessons = %s"); values.append(body.pii_scrub_lessons)
    if body.metadata_field_map is not None:
        fields.append("metadata_field_map = %s"); values.append(json.dumps(body.metadata_field_map))

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields.append("updated_at = %s"); values.append(now)
    values.append(entity_type)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE memory_entity_type_config SET {', '.join(fields)} WHERE entity_type = %s",
            values
        )

    return {"entity_type": entity_type, "updated_at": now}


# ============================================================
# MANUAL TRIGGERS
# ============================================================

@router.post("/trigger/compact/{entity_type}/{entity_id}")
async def trigger_compact_entity(
    entity_type: str,
    entity_id: str,
    admin: dict = Depends(require_admin_auth)
):
    """Manually trigger compaction (insight generation) for an entity."""
    import asyncio
    from memory_tasks import compact_entity
    asyncio.create_task(compact_entity(entity_type, entity_id))
    return {"message": "Compaction triggered", "entity_type": entity_type, "entity_id": entity_id}


@router.post("/trigger/generate-memories")
async def trigger_memory_generation(admin: dict = Depends(require_admin_auth)):
    """Manually trigger daily memory generation."""
    import asyncio
    from memory_tasks import run_daily_memory_generation
    asyncio.create_task(run_daily_memory_generation())
    return {"message": "Memory generation triggered"}


@router.post("/trigger/run-lesson-check")
async def trigger_lesson_check(admin: dict = Depends(require_admin_auth)):
    """Manually trigger the lesson accumulation check (mirrors nightly scheduler)."""
    import asyncio
    from memory_tasks import run_lesson_check
    asyncio.create_task(run_lesson_check())
    return {"message": "Lesson check triggered"}


# ============================================================
# INTERACTIONS (read-only in admin)
# ============================================================

@router.get("/admin/timeline/{entity_type}/{entity_id}")
async def admin_get_timeline(
    entity_type: str,
    entity_id: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """Admin endpoint to fetch the raw interaction timeline for an entity."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, timestamp, interaction_type, content, source, status, created_at
            FROM interactions
            WHERE primary_entity_type = %s AND primary_entity_id = %s
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """, (entity_type, entity_id, limit, offset))
        rows = cursor.fetchall()

        cursor.execute("""
            SELECT COUNT(*) as total FROM interactions 
            WHERE primary_entity_type = %s AND primary_entity_id = %s
        """, (entity_type, entity_id))
        total = cursor.fetchone()["total"]

    entries = [
        TimelineEntry(
            id=row["id"],
            timestamp=str(row["timestamp"]),
            interaction_type=row["interaction_type"],
            content_preview=(row["content"] or "")[:200],
            source=row["source"],
            status=row["status"],
        )
        for row in rows
    ]

    return {"entries": entries, "total": total, "entity_type": entity_type, "entity_id": entity_id}
    
@router.get("/interactions")
async def list_interactions(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    interaction_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """List raw interactions with filters."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if entity_type:
            conditions.append("primary_entity_type = %s"); params.append(entity_type)
        if entity_id:
            conditions.append("primary_entity_id = %s"); params.append(entity_id)
        if interaction_type:
            conditions.append("interaction_type = %s"); params.append(interaction_type)
        if status:
            conditions.append("status = %s"); params.append(status)
        if since:
            conditions.append("timestamp >= %s"); params.append(since)
        if until:
            conditions.append("timestamp <= %s"); params.append(until)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor.execute(f"SELECT COUNT(*) as total FROM interactions {where}", list(params))
        total = cursor.fetchone()["total"]

        params_page = list(params) + [limit, offset]
        cursor.execute(f"""
            SELECT id, timestamp, interaction_type, agent_id, agent_name,
                   primary_entity_type, primary_entity_id, primary_entity_subtype,
                   has_attachments, source, status, created_at
            FROM interactions {where}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """, params_page)
        rows = cursor.fetchall()

    return {"interactions": [dict(r) for r in rows], "total": total}


@router.get("/interactions/{interaction_id}")
async def get_interaction(interaction_id: str, admin: dict = Depends(require_admin_auth)):
    """Get a single interaction by ID including full content."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM interactions WHERE id = %s", (interaction_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return dict(row)


# ============================================================
# AUDIT LOG
# ============================================================

@router.get("/audit-log")
async def get_audit_log(
    agent_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """Read-only audit log viewer."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if agent_id:
            conditions.append("agent_id = %s"); params.append(agent_id)
        if action:
            conditions.append("action = %s"); params.append(action)
        if since:
            conditions.append("timestamp >= %s"); params.append(since)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params_page = list(params) + [limit, offset]
        cursor.execute(f"""
            SELECT id, agent_id, action, resource_type, resource_id, details, timestamp
            FROM memory_audit_log {where}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """, params_page)
        rows = cursor.fetchall()

    return {"entries": [dict(r) for r in rows]}


# ============================================================
# STATS
# ============================================================

@router.get("/admin/stats")
async def get_stats(admin: dict = Depends(require_admin_auth)):
    """System-wide counts across all memory tiers and interactions."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM interactions")
        total_interactions = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM memories")
        total_memories = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM insights")
        total_insights = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM insights WHERE status = 'confirmed'")
        confirmed_insights = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM lessons")
        total_lessons = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM memory_agents WHERE is_active = TRUE")
        active_agents = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM memory_agents")
        total_agents = cursor.fetchone()["total"]

        # Interactions in the last 24h
        cursor.execute("""
            SELECT COUNT(*) as total FROM interactions
            WHERE timestamp >= NOW() - INTERVAL '24 hours'
        """)
        interactions_24h = cursor.fetchone()["total"]

        # Interactions in the last 7 days
        cursor.execute("""
            SELECT COUNT(*) as total FROM interactions
            WHERE timestamp >= NOW() - INTERVAL '7 days'
        """)
        interactions_7d = cursor.fetchone()["total"]

    return {
        "interactions": {
            "total": total_interactions,
            "last_24h": interactions_24h,
            "last_7d": interactions_7d,
        },
        "memories": {"total": total_memories},
        "insights": {"total": total_insights, "confirmed": confirmed_insights},
        "lessons": {"total": total_lessons},
        "agents": {"total": total_agents, "active": active_agents},
    }


@router.get("/admin/stats/agents")
async def get_agent_stats(admin: dict = Depends(require_admin_auth)):
    """Per-agent interaction and memory counts."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                a.id,
                a.name,
                a.is_active,
                a.created_at,
                COUNT(DISTINCT i.id) AS interaction_count,
                MAX(i.timestamp)     AS last_interaction_at
            FROM memory_agents a
            LEFT JOIN interactions i ON i.agent_id = a.id
            GROUP BY a.id, a.name, a.is_active, a.created_at
            ORDER BY interaction_count DESC
        """)
        agents = cursor.fetchall()

    return {"agents": [dict(a) for a in agents]}

