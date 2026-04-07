"""
memory/agent.py — Agent-facing memory endpoints

Covers:
  - POST /interactions    : Ingest a raw interaction event
  - POST /search          : Semantic search across memories, insights, lessons
  - GET  /timeline        : Entity interaction timeline
  - GET  /insights        : List entity insights (confirmed)
  - GET  /memories        : List entity memories (daily logs)

Auth: API Key (X-API-Key header) via verify_agent_key
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.storage import get_memory_db_context, cache_interaction
from memory_models import (
    InteractionCreate, InteractionResponse,
    InsightResponse,
    MemoryResponse,
    SearchRequest, SearchResponse, SearchResult,
    TimelineRequest, TimelineEntry,
    ContextStatusResponse,
)
from memory_services import (
    generate_embedding,
    get_memory_settings,
    parse_document,
    search_memories_by_vector,
    search_insights_by_vector,
    search_lessons_by_vector,
)
from memory.auth import verify_agent_key, log_audit
from memory_tasks import check_rate_limit

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# GET /health — Memory system health check
# ============================================

@router.get("/health")
async def memory_health():
    """Health check for the memory system — no auth required."""
    from datetime import datetime, timezone
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================
# POST /interactions — Ingest a raw event
# ============================================

@router.post("/interactions", response_model=InteractionResponse)
async def ingest_interaction(
    body: InteractionCreate,
    agent: dict = Depends(verify_agent_key)
):
    """
    Ingest a raw interaction event.

    Flow:
      1. Rate-limit check (per agent)
      2. Parse attachments immediately (if any)
      3. Write to PostgreSQL interactions table (status=pending)
      4. Write to Redis cache (24h TTL)
      5. Return interaction ID + status
    """
    if not check_rate_limit(agent["id"]):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()
    interaction_id = str(uuid.uuid4())

    # Parse attachments inline if present
    attachment_refs = list(body.attachment_refs or [])
    content = body.content

    for attachment in attachment_refs:
        attach_type = attachment.get("type", "base64")
        raw_blob = None
        
        # 1. Acquire bytes
        if attach_type == "url":
            url = attachment.get("url")
            if url:
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        raw_blob = resp.content
                except Exception as e:
                    logger.warning(f"Failed to fetch attachment URL {url}: {e}")
        else:
            b64_data = attachment.get("data") or attachment.get("raw_bytes")
            if b64_data:
                import base64
                try:
                    raw_blob = base64.b64decode(b64_data)
                except Exception as e:
                    logger.warning(f"Failed to decode base64 attachment: {e}")

        if not raw_blob:
            continue

        # 2. MIME Inference
        import filetype
        inferred_mime = None
        kind = filetype.guess(raw_blob)
        if kind:
            inferred_mime = kind.mime
        
        mime_type = inferred_mime or attachment.get("mime_type", "application/octet-stream")
        filename = attachment.get("filename", "attachment")

        # 3. Ship to Document Parser
        parsed = await parse_document(raw_blob, filename, mime_type)
        if parsed.get("text"):
            content += f"\n\n---\n[Attachment ({mime_type}): {filename}]\n{parsed['text']}"
            attachment["parsed_content"] = parsed["text"]
            attachment["inferred_mime"] = mime_type

    # Write interaction to PostgreSQL
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO interactions (
                id, timestamp, interaction_type, agent_id, agent_name,
                content, primary_entity_type, primary_entity_subtype, primary_entity_id,
                metadata, metadata_field_map, has_attachments, attachment_refs,
                source, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            interaction_id,
            now,
            body.interaction_type,
            agent["id"],
            body.agent_name or agent.get("name"),
            content,
            body.primary_entity_type,
            body.primary_entity_subtype,
            body.primary_entity_id,
            json.dumps(body.metadata or {}),
            json.dumps(body.metadata_field_map or {}),
            body.has_attachments,
            json.dumps(attachment_refs),
            body.source,
            "pending",
            now,
        ))

    # Cache in Redis for 24h hot-path access by the daily generation job
    cache_interaction(interaction_id, {
        "id": interaction_id,
        "interaction_type": body.interaction_type,
        "agent_id": agent["id"],
        "content": content,
        "primary_entity_type": body.primary_entity_type,
        "primary_entity_id": body.primary_entity_id,
        "timestamp": now,
        "metadata_field_map": body.metadata_field_map or {},
    })

    log_audit(agent["id"], "ingest_interaction", "interaction", interaction_id, {
        "interaction_type": body.interaction_type,
        "entity": f"{body.primary_entity_type}/{body.primary_entity_id}",
    })

    return InteractionResponse(
        id=interaction_id,
        timestamp=now,
        interaction_type=body.interaction_type,
        agent_id=agent["id"],
        agent_name=body.agent_name or agent.get("name"),
        primary_entity_type=body.primary_entity_type,
        primary_entity_id=body.primary_entity_id,
        primary_entity_subtype=body.primary_entity_subtype,
        has_attachments=body.has_attachments,
        source=body.source,
        status="pending",
        created_at=now,
    )


# ============================================
# POST /search — Semantic search
# ============================================

@router.post("/search", response_model=SearchResponse)
async def search_memory(
    request: SearchRequest,
    agent: dict = Depends(verify_agent_key)
):
    """
    Fan-out semantic search across memories, insights, and lessons.
    Results merged and returned ordered by score.
    """
    query_embedding = await generate_embedding(request.query)
    if not query_embedding:
        return SearchResponse(results=[], total=0, query=request.query)

    results: list[SearchResult] = []
    layers = request.layers.lower()

    if layers in ("memories", "all"):
        mem_hits = await search_memories_by_vector(
            query_embedding,
            entity_id=request.entity_id,
            entity_type=request.entity_type,
            limit=request.limit,
        )
        for hit in mem_hits:
            results.append(SearchResult(
                id=hit["id"],
                layer="memory",
                score=float(hit.get("score", 0)),
                name=None,
                snippet=(hit.get("content_summary") or "")[:200],
                entity_id=hit["primary_entity_id"],
                entity_type=hit["primary_entity_type"],
                created_at=str(hit.get("created_at", "")),
            ))

    if layers in ("insights", "all"):
        ins_hits = await search_insights_by_vector(
            query_embedding,
            entity_id=request.entity_id,
            entity_type=request.entity_type,
            limit=request.limit,
        )
        for hit in ins_hits:
            results.append(SearchResult(
                id=hit["id"],
                layer="insight",
                score=float(hit.get("score", 0)),
                name=hit.get("name"),
                snippet=(hit.get("summary") or "")[:200],
                entity_id=hit["primary_entity_id"],
                entity_type=hit["primary_entity_type"],
                created_at=str(hit.get("created_at", "")),
            ))

    if layers in ("lessons", "all"):
        les_hits = await search_lessons_by_vector(
            query_embedding,
            limit=request.limit,
        )
        for hit in les_hits:
            results.append(SearchResult(
                id=hit["id"],
                layer="lesson",
                score=float(hit.get("score", 0)),
                name=hit.get("name"),
                snippet=(hit.get("summary") or "")[:200],
                entity_id=None,
                entity_type=None,
                created_at=str(hit.get("created_at", "")),
            ))

    # Sort merged results by score descending, paginate
    results.sort(key=lambda r: r.score, reverse=True)
    paginated = results[request.offset: request.offset + request.limit]

    log_audit(agent["id"], "search", "memory", None, {"query": request.query, "layers": layers})
    return SearchResponse(results=paginated, total=len(results), query=request.query)


# ============================================
# GET /has-context — Check Context Existence
# ============================================

@router.get("/has-context", response_model=ContextStatusResponse)
async def get_has_context(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    agent: dict = Depends(verify_agent_key)
):
    """Check if any context exists for an entity and return IDs and dates."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Interactions
        cursor.execute("""
            SELECT id, timestamp
            FROM interactions
            WHERE primary_entity_type = %s AND primary_entity_id = %s
            ORDER BY timestamp DESC
        """, (entity_type, entity_id))
        i_rows = cursor.fetchall()
        i_ids = [r["id"] for r in i_rows]
        i_last = str(i_rows[0]["timestamp"]) if i_rows else None
        
        # Memories
        cursor.execute("""
            SELECT id, date
            FROM memories
            WHERE primary_entity_type = %s AND primary_entity_id = %s
            ORDER BY date DESC
        """, (entity_type, entity_id))
        m_rows = cursor.fetchall()
        m_ids = [r["id"] for r in m_rows]
        m_last = str(m_rows[0]["date"]) if m_rows else None
        
        # Insights
        cursor.execute("""
            SELECT id, created_at
            FROM insights
            WHERE primary_entity_type = %s AND primary_entity_id = %s
            ORDER BY created_at DESC
        """, (entity_type, entity_id))
        ins_rows = cursor.fetchall()
        ins_ids = [r["id"] for r in ins_rows]
        ins_last = str(ins_rows[0]["created_at"]) if ins_rows else None
        
    total = len(i_ids) + len(m_ids) + len(ins_ids)

    return ContextStatusResponse(
        has_context=(total > 0),
        interactions_count=len(i_ids),
        last_interaction_date=i_last,
        interactions_ids=i_ids,
        memories_count=len(m_ids),
        last_memory_date=m_last,
        memories_ids=m_ids,
        insights_count=len(ins_ids),
        last_insight_date=ins_last,
        insights_ids=ins_ids
    )


# ============================================
# GET /timeline — Entity interaction history
# ============================================

@router.get("/timeline")
async def get_timeline(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    interaction_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    agent: dict = Depends(verify_agent_key)
):
    """Return raw interaction timeline for an entity."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = [
            "primary_entity_type = %s",
            "primary_entity_id = %s",
        ]
        params: list = [entity_type, entity_id]

        if since:
            conditions.append("timestamp >= %s")
            params.append(since)
        if until:
            conditions.append("timestamp <= %s")
            params.append(until)
        if interaction_type:
            conditions.append("interaction_type = %s")
            params.append(interaction_type)

        where = " AND ".join(conditions)
        params += [limit, offset]

        cursor.execute(f"""
            SELECT id, timestamp, interaction_type, content, source, status, created_at
            FROM interactions
            WHERE {where}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """, params)

        rows = cursor.fetchall()

        cursor.execute(f"""
            SELECT COUNT(*) as total FROM interactions WHERE {where}
        """, params[:-2])
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


# ============================================
# GET /memories — Entity daily memory logs
# ============================================

@router.get("/memories")
async def get_memories(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    compacted: Optional[bool] = Query(None),
    limit: int = Query(30, le=100),
    offset: int = Query(0),
    agent: dict = Depends(verify_agent_key)
):
    """Return Tier 1 memory logs for an entity."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = [
            "primary_entity_type = %s",
            "primary_entity_id = %s",
        ]
        params: list = [entity_type, entity_id]

        if since:
            conditions.append("date >= %s")
            params.append(since)
        if until:
            conditions.append("date <= %s")
            params.append(until)
        if compacted is not None:
            conditions.append("compacted = %s")
            params.append(compacted)

        where = " AND ".join(conditions)
        params += [limit, offset]

        cursor.execute(f"""
            SELECT id, date, primary_entity_type, primary_entity_id,
                   interaction_count, content_summary, related_entities,
                   intents, compacted, created_at
            FROM memories
            WHERE {where}
            ORDER BY date DESC
            LIMIT %s OFFSET %s
        """, params)

        rows = cursor.fetchall()

    return {"memories": [dict(r) for r in rows], "entity_type": entity_type, "entity_id": entity_id}


# ============================================
# GET /insights — Entity confirmed insights
# ============================================

@router.get("/insights")
async def get_insights(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    status: Optional[str] = Query("confirmed"),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    agent: dict = Depends(verify_agent_key)
):
    """Return Tier 2 insights for an entity."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions = [
            "primary_entity_type = %s",
            "primary_entity_id = %s",
        ]
        params: list = [entity_type, entity_id]

        if status:
            conditions.append("status = %s")
            params.append(status)

        where = " AND ".join(conditions)
        params += [limit, offset]

        cursor.execute(f"""
            SELECT id, primary_entity_type, primary_entity_id, source_memory_ids,
                   insight_type, name, content, summary, status,
                   created_by, confirmed_by, confirmed_at, created_at, updated_at
            FROM insights
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params)

        rows = cursor.fetchall()

    return {"insights": [dict(r) for r in rows], "entity_type": entity_type, "entity_id": entity_id}
