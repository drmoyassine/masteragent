"""
memory/admin.py — Admin endpoints for the Memory System

Provides:
  - PrivateKnowledge CRUD (Tier 2): list, get, create, update status, delete
  - PublicKnowledge CRUD (Tier 3): list, get, create, update, delete, promote from PrivateKnowledge
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
    InteractionResponse, InteractionUpdate, TimelineEntry,
    SearchRequest, SearchResponse, SearchResult, MemoryUpdate,
    OutboundWebhookCreate, OutboundWebhookUpdate, OutboundWebhookResponse
)
from memory_services import (
    generate_embedding, search_memories_by_vector,
    search_insights_by_vector, search_lessons_by_vector,
    get_memory_settings
)
from memory.auth import require_admin_auth

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# private_knowledge (Tier 2)
# ============================================================

@router.get("/private_knowledge")
async def list_insights(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),      # draft | confirmed | archived
    knowledge_type: Optional[str] = Query(None),
    limit: int = Query(30, le=100),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """List private_knowledge with optional filters."""
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
        if knowledge_type:
            conditions.append("knowledge_type = %s")
            params.append(knowledge_type)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params_count = list(params)
        cursor.execute(f"SELECT COUNT(*) as total FROM private_knowledge {where}", params_count)
        total = cursor.fetchone()["total"]

        params += [limit, offset]
        cursor.execute(f"""
            SELECT id, seq_id, primary_entity_type, primary_entity_id, source_memory_ids,
                   knowledge_type, name, content, summary, status,
                   created_by, confirmed_by, confirmed_at, created_at, updated_at
            FROM private_knowledge {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params)
        rows = cursor.fetchall()

    return {"private_knowledge": [dict(r) for r in rows], "total": total}


@router.get("/private_knowledge/{insight_id}")
async def get_insight(insight_id: str, admin: dict = Depends(require_admin_auth)):
    """Get a single PrivateKnowledge by ID."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM private_knowledge WHERE id = %s", (insight_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="PrivateKnowledge not found")
    return dict(row)


@router.post("/private_knowledge")
async def create_insight(body: InsightCreate, admin: dict = Depends(require_admin_auth)):
    """Manually create an PrivateKnowledge (draft)."""
    insight_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO private_knowledge (
                id, primary_entity_type, primary_entity_id, source_memory_ids,
                knowledge_type, name, content, summary,
                status, created_by, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            insight_id, body.primary_entity_type, body.primary_entity_id,
            body.source_memory_ids or [],
            body.knowledge_type, body.name, body.content, body.summary,
            "draft", "admin", now, now
        ))

    return {"id": insight_id, "status": "draft", "created_at": now}


@router.patch("/private_knowledge/{insight_id}")
async def update_insight(
    insight_id: str,
    body: InsightUpdate,
    admin: dict = Depends(require_admin_auth)
):
    """Update an PrivateKnowledge's fields or status (confirm/archive)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status FROM private_knowledge WHERE id = %s", (insight_id,))
        existing = cursor.fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="PrivateKnowledge not found")

    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []

    if body.name is not None:
        fields.append("name = %s"); values.append(body.name)
    if body.content is not None:
        fields.append("content = %s"); values.append(body.content)
    if body.summary is not None:
        fields.append("summary = %s"); values.append(body.summary)
    if body.knowledge_type is not None:
        fields.append("knowledge_type = %s"); values.append(body.knowledge_type)
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
            f"UPDATE private_knowledge SET {', '.join(fields)} WHERE id = %s",
            values
        )

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM private_knowledge WHERE id = %s", (insight_id,))
        updated = cursor.fetchone()

    return dict(updated) if updated else {"id": insight_id, "updated_at": now}


@router.delete("/private_knowledge/{insight_id}", status_code=204)
async def delete_insight(insight_id: str, admin: dict = Depends(require_admin_auth)):
    """Delete an PrivateKnowledge."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM private_knowledge WHERE id = %s", (insight_id,))


@router.post("/private_knowledge/{insight_id}/promote")
async def promote_insight_to_lesson(
    insight_id: str,
    admin: dict = Depends(require_admin_auth)
):
    """Manually promote a confirmed PrivateKnowledge to a PublicKnowledge (async background job)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM private_knowledge WHERE id = %s", (insight_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="PrivateKnowledge not found")

    # Enqueue promotion job directly to orchestrator
    from memory.queue import knowledge_queue
    await knowledge_queue.add("promote_to_lesson", {"insight_id": insight_id})
    return {"message": "Promotion queued", "insight_id": insight_id}


# ============================================================
# public_knowledge (Tier 3)
# ============================================================

@router.get("/public_knowledge")
async def list_lessons(
    knowledge_type: Optional[str] = Query(None),
    visibility: Optional[str] = Query(None),
    limit: int = Query(30, le=100),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """List public_knowledge with optional filters."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if knowledge_type:
            conditions.append("knowledge_type = %s"); params.append(knowledge_type)
        if visibility:
            conditions.append("visibility = %s"); params.append(visibility)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params_count = list(params)
        cursor.execute(f"SELECT COUNT(*) as total FROM public_knowledge {where}", params_count)
        total = cursor.fetchone()["total"]

        params += [limit, offset]
        cursor.execute(f"""
            SELECT id, seq_id, source_private_knowledge_ids, knowledge_type, name, content,
                   summary, visibility, tags, created_at, updated_at
            FROM public_knowledge {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params)
        rows = cursor.fetchall()

    return {"public_knowledge": [dict(r) for r in rows], "total": total}


@router.get("/public_knowledge/{lesson_id}")
async def get_lesson(lesson_id: str, admin: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM public_knowledge WHERE id = %s", (lesson_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="PublicKnowledge not found")
    return dict(row)


@router.post("/public_knowledge")
async def create_lesson(body: LessonCreate, admin: dict = Depends(require_admin_auth)):
    """Manually create a PublicKnowledge."""
    lesson_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO public_knowledge (
                id, source_private_knowledge_ids, knowledge_type, name, content, summary,
                visibility, tags, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            lesson_id, body.source_private_knowledge_ids or [],
            body.knowledge_type, body.name, body.content, body.summary,
            body.visibility, body.tags or [], now, now
        ))

    return {"id": lesson_id, "created_at": now}


@router.patch("/public_knowledge/{lesson_id}")
async def update_lesson(
    lesson_id: str,
    body: LessonUpdate,
    admin: dict = Depends(require_admin_auth)
):
    """Update a PublicKnowledge's fields."""
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []

    if body.name is not None:
        fields.append("name = %s"); values.append(body.name)
    if body.content is not None:
        fields.append("content = %s"); values.append(body.content)
    if body.summary is not None:
        fields.append("summary = %s"); values.append(body.summary)
    if body.knowledge_type is not None:
        fields.append("knowledge_type = %s"); values.append(body.knowledge_type)
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
            f"UPDATE public_knowledge SET {', '.join(fields)} WHERE id = %s",
            values
        )

    return {"id": lesson_id, "updated_at": now}


@router.delete("/public_knowledge/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: str, admin: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM public_knowledge WHERE id = %s", (lesson_id,))


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
    """Manually trigger compaction (PrivateKnowledge generation) for an entity via queue drop."""
    from memory.queue import knowledge_queue
    await knowledge_queue.add("generate_insight", {"entity_type": entity_type, "entity_id": entity_id}, {"priority": 1})
    return {"message": "Compaction triggered via queue", "entity_type": entity_type, "entity_id": entity_id}


@router.post("/trigger/generate-memories")
async def trigger_memory_generation(
    include_today: bool = Query(False, description="Whether to include interactions logged today"),
    admin: dict = Depends(require_admin_auth)
):
    """Manually trigger daily memory generation. Iterates and enqueues payload synchronously, no LLM cost."""
    from memory_tasks import run_daily_memory_generation
    await run_daily_memory_generation(include_today=include_today)
    return {"message": "Memory generation queueing completed", "include_today": include_today}


@router.post("/trigger/run-PublicKnowledge-check")
async def trigger_lesson_check(admin: dict = Depends(require_admin_auth)):
    """Manually trigger the PublicKnowledge accumulation check via queue drop."""
    from memory.queue import knowledge_queue
    await knowledge_queue.add("generate_lesson", {}, {"priority": 1})
    return {"message": "PublicKnowledge check queued"}


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
            SELECT id, seq_id, timestamp, interaction_type, content, source, status, created_at
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
            seq_id=row["seq_id"],
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
    entity_types: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    interaction_type: Optional[str] = Query(None),
    interaction_types: Optional[str] = Query(None),
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
        
        final_entity_types = []
        if entity_type and entity_type != 'all': final_entity_types.append(entity_type)
        if entity_types: final_entity_types.extend([x.strip() for x in entity_types.split(',') if x.strip() and x.strip() != 'all'])
            
        final_interaction_types = []
        if interaction_type and interaction_type != 'all': final_interaction_types.append(interaction_type)
        if interaction_types: final_interaction_types.extend([x.strip() for x in interaction_types.split(',') if x.strip() and x.strip() != 'all'])

        if final_entity_types:
            conditions.append("primary_entity_type = ANY(%s)"); params.append(final_entity_types)
        if entity_id:
            conditions.append("primary_entity_id = %s"); params.append(entity_id)
        if final_interaction_types:
            conditions.append("interaction_type = ANY(%s)"); params.append(final_interaction_types)
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
            SELECT id, seq_id, timestamp, interaction_type, agent_id, agent_name,
                   primary_entity_type, primary_entity_id, primary_entity_subtype,
                   has_attachments, source, status, created_at, content, processing_errors
            FROM interactions {where}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """, params_page)
        rows = cursor.fetchall()

    return {"interactions": [dict(r) for r in rows], "total": total}

@router.get("/interactions/filter-options")
async def get_interaction_filter_options(
    entity_types: Optional[str] = Query(None),
    interaction_types: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    admin: dict = Depends(require_admin_auth)
):
    """Dynamic Filter Cross-Resolution."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        def get_valid_options(target_field: str, ignore_filter: str):
            conditions = []
            params = []
            
            if ignore_filter != "interaction_types" and interaction_types:
                lst = [x.strip() for x in interaction_types.split(',') if x.strip() and x.strip() != 'all']
                if lst:
                    conditions.append("interaction_type = ANY(%s)")
                    params.append(lst)
                    
            if ignore_filter != "entity_types" and entity_types:
                lst = [x.strip() for x in entity_types.split(',') if x.strip() and x.strip() != 'all']
                if lst:
                    conditions.append("primary_entity_type = ANY(%s)")
                    params.append(lst)
            
            if entity_id:
                conditions.append("primary_entity_id = %s"); params.append(entity_id)
            if since:
                conditions.append("timestamp >= %s"); params.append(since)
            if until:
                conditions.append("timestamp <= %s"); params.append(until)
                
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            cursor.execute(f"SELECT DISTINCT {target_field} FROM interactions {where} ORDER BY {target_field}", params)
            return [r[target_field] for r in cursor.fetchall() if r[target_field]]

        return {
            "entity_types": get_valid_options("primary_entity_type", "entity_types"),
            "interaction_types": get_valid_options("interaction_type", "interaction_types")
        }


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


@router.put("/interactions/{interaction_id}")
async def update_interaction(
    interaction_id: str,
    payload: InteractionUpdate,
    admin: dict = Depends(require_admin_auth)
):
    """Update a pending interaction's fields."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Verify interaction exists and is pending
        cursor.execute("SELECT status FROM interactions WHERE id = %s", (interaction_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Interaction not found")
            
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail="Only pending interactions can be edited")

        updates = []
        params = []
        
        if payload.interaction_type is not None:
            updates.append("interaction_type = %s")
            params.append(payload.interaction_type)
        if payload.primary_entity_type is not None:
            updates.append("primary_entity_type = %s")
            params.append(payload.primary_entity_type)
        if payload.primary_entity_id is not None:
            updates.append("primary_entity_id = %s")
            params.append(payload.primary_entity_id)
        if payload.primary_entity_subtype is not None:
            updates.append("primary_entity_subtype = %s")
            params.append(payload.primary_entity_subtype)
        if payload.content is not None:
            updates.append("content = %s")
            params.append(payload.content)
        if payload.source is not None:
            updates.append("source = %s")
            params.append(payload.source)
        if payload.status is not None:
            updates.append("status = %s")
            params.append(payload.status)

        if not updates:
            return {"status": "no internal updates"}

        params.append(interaction_id)
        query = f"UPDATE interactions SET {', '.join(updates)} WHERE id = %s"
        cursor.execute(query, params)
        conn.commit()

    return {"status": "updated"}

@router.post("/interactions/bulk-delete")
async def bulk_delete_interactions(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth)
):
    """Bulk delete an array of interactions natively"""
    interaction_ids = payload.get("interaction_ids", [])
    if not interaction_ids:
        return {"deleted": 0}
        
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM interactions WHERE id = ANY(%s)", (interaction_ids,))
        deleted = cursor.rowcount
    return {"deleted": deleted}

@router.post("/interactions/bulk-reprocess")
async def bulk_reprocess_interactions(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth)
):
    """Bulk re-process an array of interactions via native BullMQ sequencing"""
    from memory.queue import memory_bulk_queue
    interaction_ids = payload.get("interaction_ids", [])
    if not interaction_ids:
        return {"queued": 0}

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        # Immediately reset error states and flags to cleanly re-read sequence.
        cursor.execute(
            "UPDATE interactions SET status = 'pending', processing_errors = '{}' WHERE id = ANY(%s)",
            (interaction_ids,)
        )
        
    queued_count = 0
    # Linearly drop into Redis Array (this honors memory sleep configurations in the worker task natively)
    for i_id in interaction_ids:
        await memory_bulk_queue.add("reprocess", {"interaction_id": i_id})
        queued_count += 1
        
    return {"queued": queued_count}

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

        cursor.execute("SELECT COUNT(*) as total FROM private_knowledge")
        total_insights = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM private_knowledge WHERE status = 'confirmed'")
        confirmed_insights = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM public_knowledge")
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
        "private_knowledge": {"total": total_insights, "confirmed": confirmed_insights},
        "public_knowledge": {"total": total_lessons},
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

# ============================================================
# DASHBOARD / EXPLORER ENDPOINTS
# ============================================================

@router.get("/admin/daily/{date_str}")
async def admin_get_daily_memories(
    date_str: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """Fetch daily memories for the explorer UI."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, seq_id, date, primary_entity_type, primary_entity_id,
                   interaction_count, content_summary, related_entities,
                   intents, compacted, processing_errors, created_at
            FROM memories
            WHERE date = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (date_str, limit, offset))
        rows = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) as total FROM memories WHERE date = %s", (date_str,))
        total = cursor.fetchone()["total"]

    return {"memories": [dict(r) for r in rows], "total": total}

@router.get("/admin/memories")
async def list_admin_memories(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    admin: dict = Depends(require_admin_auth)
):
    """Fetch paginated memories globally."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if entity_type:
            conditions.append("primary_entity_type = %s"); params.append(entity_type)
        if entity_id:
            conditions.append("primary_entity_id = %s"); params.append(entity_id)
        if start_date: 
            conditions.append("date >= %s"); params.append(start_date)
        if end_date: 
            conditions.append("date <= %s"); params.append(end_date)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor.execute(f"SELECT COUNT(*) as total FROM memories {where}", list(params))
        total = cursor.fetchone()["total"]

        params_page = list(params) + [limit, offset]
        cursor.execute(f"""
            SELECT id, seq_id, date, primary_entity_type, primary_entity_id,
                   interaction_count, content_summary, related_entities,
                   intents, compacted, processing_errors, created_at
            FROM memories {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params_page)
        rows = cursor.fetchall()

    return {"memories": [dict(r) for r in rows], "total": total}

@router.get("/admin/memories/{memory_id}")
async def admin_get_memory_detail(memory_id: str, admin: dict = Depends(require_admin_auth)):
    """Fetch a single memory details."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE id = %s", (memory_id,))
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")
    return dict(row)

@router.patch("/admin/memories/{memory_id}")
async def admin_update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    admin: dict = Depends(require_admin_auth)
):
    """Update a memory's properties (content_summary, intents, etc)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM memories WHERE id = %s", (memory_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Memory not found")

        updates = []
        params = []

        if payload.content_summary is not None:
            updates.append("content_summary = %s")
            params.append(payload.content_summary)
            
        if payload.related_entities is not None:
            updates.append("related_entities = %s")
            params.append(json.dumps([e.model_dump() if hasattr(e, "model_dump") else e for e in payload.related_entities]))

        if payload.intents is not None:
            updates.append("intents = %s")
            params.append(payload.intents)

        if payload.compacted is not None:
            updates.append("compacted = %s")
            params.append(payload.compacted)

        if not updates:
            return {"status": "no internal updates"}

        updates.append("updated_at = NOW()")
        params.append(memory_id)
        
        query = f"UPDATE memories SET {', '.join(updates)} WHERE id = %s"
        cursor.execute(query, params)
        conn.commit()
    
    return {"status": "updated"}

@router.delete("/admin/memories/{memory_id}", status_code=204)
async def admin_delete_memory(memory_id: str, admin: dict = Depends(require_admin_auth)):
    """Delete a memory from the system."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
        conn.commit()

@router.post("/admin/memories/bulk-delete")
async def bulk_delete_memories(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth)
):
    """Bulk delete memories natively."""
    memory_ids = payload.get("memory_ids", [])
    if not memory_ids:
        return {"deleted": 0}

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = ANY(%s)", (memory_ids,))
        deleted = cursor.rowcount
        conn.commit()
    return {"deleted": deleted}

@router.post("/admin/memories/bulk-reprocess")
async def bulk_reprocess_memories(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth)
):
    """Delete memories and enqueue their interactions back into memory pipeline generation."""
    from memory.queue import memory_queue
    memory_ids = payload.get("memory_ids", [])
    if not memory_ids:
        return {"queued": 0}

    queued_count = 0
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, primary_entity_type, primary_entity_id, date, interaction_ids FROM memories WHERE id = ANY(%s)", (memory_ids,))
        memories = cursor.fetchall()

        settings = get_memory_settings()
        retries = int(settings.get("memory_queue_retries", 3))
        delay = int(settings.get("memory_queue_retry_delay", 2000))
        
        for mem in memories:
            i_ids = mem.get("interaction_ids", [])
            if hasattr(i_ids, "tolist"):
                i_ids = i_ids.tolist()
            if isinstance(i_ids, str):
                import ast
                if i_ids.startswith("{"):
                    i_ids = i_ids.replace("{","[").replace("}","]")
                    try:
                        i_ids = ast.literal_eval(i_ids)
                    except Exception:
                        i_ids = []
            
            if i_ids:
                cursor.execute(
                    "UPDATE interactions SET status = 'pending', processing_errors = '{}', embedding = NULL WHERE id = ANY(%s)", 
                    (i_ids,)
                )
            
            cursor.execute("DELETE FROM memories WHERE id = %s", (mem["id"],))
            
            # Requeue background job for generation
            # Date can safely be str representation for memory tasks
            await memory_queue.add("generate_memory", {
                "entity_type": mem["primary_entity_type"],
                "entity_id": mem["primary_entity_id"],
                "interaction_date": str(mem["date"])
            }, {"priority": 5, "attempts": retries, "backoff": {"type": "exponential", "delay": delay}})
            queued_count += 1
            
        conn.commit()
        
    return {"queued": queued_count}

@router.post("/admin/search", response_model=SearchResponse)
async def admin_search_memories(
    request: SearchRequest,
    admin: dict = Depends(require_admin_auth)
):
    """Semantic search accessible via the dashboard UI."""
    query_embedding = await generate_embedding(request.query)
    if not query_embedding:
        return SearchResponse(results=[], total=0, query=request.query)

    results: list[SearchResult] = []
    layers = request.layers.lower()

    if layers in ("memories", "all"):
        mem_hits = await search_memories_by_vector(query_embedding, request.entity_id, request.entity_type, request.limit)
        for hit in mem_hits:
            results.append(SearchResult(
                id=hit["id"], layer="memory", score=float(hit.get("score", 0)),
                name=None, snippet=(hit.get("content_summary") or "")[:200],
                entity_id=hit["primary_entity_id"], entity_type=hit["primary_entity_type"],
                created_at=str(hit.get("created_at", ""))
            ))

    if layers in ("private_knowledge", "all"):
        ins_hits = await search_insights_by_vector(query_embedding, request.entity_id, request.entity_type, request.limit)
        for hit in ins_hits:
            results.append(SearchResult(
                id=hit["id"], layer="PrivateKnowledge", score=float(hit.get("score", 0)),
                name=hit.get("name"), snippet=(hit.get("summary") or "")[:200],
                entity_id=hit["primary_entity_id"], entity_type=hit["primary_entity_type"],
                created_at=str(hit.get("created_at", ""))
            ))

    if layers in ("public_knowledge", "all"):
        les_hits = await search_lessons_by_vector(query_embedding, request.limit)
        for hit in les_hits:
            results.append(SearchResult(
                id=hit["id"], layer="PublicKnowledge", score=float(hit.get("score", 0)),
                name=hit.get("name"), snippet=(hit.get("summary") or "")[:200],
                entity_id=None, entity_type=None, created_at=str(hit.get("created_at", ""))
            ))

    results.sort(key=lambda r: r.score, reverse=True)
    paginated = results[request.offset: request.offset + request.limit]
    return SearchResponse(results=paginated, total=len(results), query=request.query)

# ============================================================
# OUTBOUND WEBHOOKS
# ============================================================

@router.get("/outbound-webhooks")
async def list_outbound_webhooks(admin: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_outbound_webhooks ORDER BY created_at DESC")
        rows = cursor.fetchall()

    return {"outbound_webhooks": [dict(r) for r in rows]}

@router.post("/outbound-webhooks")
async def create_outbound_webhook(body: OutboundWebhookCreate, admin: dict = Depends(require_admin_auth)):
    webhook_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_outbound_webhooks (
                id, name, url, debounce_ms, conditions, payload_mode, include_latest_memory, is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            webhook_id, body.name, body.url, body.debounce_ms, json.dumps(body.conditions or {}), body.payload_mode,
            body.include_latest_memory, body.is_active, now, now
        ))
        
    return {"id": webhook_id, "created_at": now}

@router.patch("/outbound-webhooks/{webhook_id}")
async def update_outbound_webhook(webhook_id: str, body: OutboundWebhookUpdate, admin: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []

    if body.name is not None:
        fields.append("name = %s"); values.append(body.name)
    if body.url is not None:
        fields.append("url = %s"); values.append(body.url)
    if body.debounce_ms is not None:
        fields.append("debounce_ms = %s"); values.append(body.debounce_ms)
    if body.conditions is not None:
        fields.append("conditions = %s"); values.append(json.dumps(body.conditions))
    if body.payload_mode is not None:
        fields.append("payload_mode = %s"); values.append(body.payload_mode)
    if body.include_latest_memory is not None:
        fields.append("include_latest_memory = %s"); values.append(body.include_latest_memory)
    if body.is_active is not None:
        fields.append("is_active = %s"); values.append(body.is_active)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields.append("updated_at = %s"); values.append(now)
    values.append(webhook_id)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE memory_outbound_webhooks SET {', '.join(fields)} WHERE id = %s",
            values
        )

    return {"id": webhook_id, "updated_at": now}

@router.delete("/outbound-webhooks/{webhook_id}", status_code=204)
async def delete_outbound_webhook(webhook_id: str, admin: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_outbound_webhooks WHERE id = %s", (webhook_id,))



