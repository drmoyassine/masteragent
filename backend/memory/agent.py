"""
memory/agent.py — Agent-facing memory endpoints

Unified REST SDK architecture for AI Agents.
Exposes standard CRUD operations across all four memory tiers with strict entity scoping.
All endpoints use the Agent API Key validation.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from core.storage import get_memory_db_context, cache_interaction, flush_interaction_cache
from memory_models import (
    InteractionCreate, InteractionResponse, InteractionUpdate,
    MemoryCreate, MemoryUpdate, MemoryResponse,
    IntelligenceCreate, IntelligenceUpdate, IntelligenceResponse,
    KnowledgeCreate, KnowledgeUpdate, KnowledgeResponse,
    SearchRequest, SearchResponse, SearchResult,
    ContextStatusResponse,
)
from memory_services import (
    generate_embedding,
    parse_document,
    search_interactions_by_vector,
    search_interactions_by_fulltext,
    search_memories_by_vector,
    search_memories_by_fulltext,
    search_intelligence_by_vector,
    search_intelligence_by_fulltext,
    search_knowledge_by_vector,
    search_knowledge_by_fulltext,
)
from memory.auth import verify_agent_key, log_audit
from memory_tasks import check_rate_limit

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================
# TIER 0: 🔄 Interactions
# ============================================

@router.post("/interactions", response_model=InteractionResponse, tags=["🔄 Interactions"], status_code=202)
async def ingest_interaction(
    body: InteractionCreate,
    response: Response,
    agent: dict = Depends(verify_agent_key)
):
    """Ingest a raw interaction event, insert as pending, and enqueue for processing."""
    if not check_rate_limit(agent["id"]):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()
    interaction_id = str(uuid.uuid4())

    attachment_refs = list(body.attachment_refs or [])
    content = body.content

    # Insert bare row (state=pending) to PostgreSQL
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO interactions (
                id, timestamp, interaction_type, agent_id, agent_name,
                content, primary_entity_type, primary_entity_subtype, primary_entity_id,
                metadata, metadata_field_map, has_attachments, attachment_refs,
                processing_errors, source, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            interaction_id, now, body.interaction_type, agent["id"], body.agent_name or agent.get("name"),
            content, body.primary_entity_type, body.primary_entity_subtype, body.primary_entity_id,
            json.dumps(body.metadata or {}, ensure_ascii=False), json.dumps(body.metadata_field_map or {}, ensure_ascii=False),
            body.has_attachments, json.dumps(attachment_refs, ensure_ascii=False), json.dumps({}), body.source, "pending", now
        ))
        # Ensure commit happens here seamlessly by context manager exiting before passing to BullMQ

    # Enqueue standard DLQ compliant backend task
    from memory.queue import interactions_queue
    await interactions_queue.add(
        "ingest_interaction", 
        {"interaction_id": interaction_id}, 
        {"attempts": 3, "backoff": {"type": "exponential", "delay": 2000}}
    )

    log_audit(agent["id"], "ingest_interaction", "interaction", interaction_id, {
        "interaction_type": body.interaction_type,
        "entity": f"{body.primary_entity_type}/{body.primary_entity_id}",
    })

    # Return HTTP 202 Accepted instantly
    response.status_code = 202
    return InteractionResponse(
        id=interaction_id, timestamp=now, interaction_type=body.interaction_type,
        agent_id=agent["id"], agent_name=body.agent_name or agent.get("name"),
        primary_entity_type=body.primary_entity_type, primary_entity_id=body.primary_entity_id,
        primary_entity_subtype=body.primary_entity_subtype, has_attachments=body.has_attachments,
        source=body.source, status="pending", created_at=now
    )


@router.get("/interactions", tags=["🔄 Interactions"])
async def list_interactions(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    entity_subtype: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    agent: dict = Depends(verify_agent_key)
):
    """Retrieve the interaction timeline for an entity."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions, params = ["primary_entity_type = %s", "primary_entity_id = %s"], [entity_type, entity_id]
        if entity_subtype: conditions.append("primary_entity_subtype = %s"); params.append(entity_subtype)
        if start_date: conditions.append("timestamp >= %s"); params.append(start_date)
        if end_date: conditions.append("timestamp <= %s"); params.append(end_date)
        if status: conditions.append("status = %s"); params.append(status)

        where = " AND ".join(conditions)
        
        cursor.execute(f"SELECT COUNT(*) as total FROM interactions WHERE {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT id, seq_id, timestamp, interaction_type, agent_id, agent_name,
                   primary_entity_type, primary_entity_id, primary_entity_subtype,
                   has_attachments, source, status, created_at, content
            FROM interactions WHERE {where}
            ORDER BY timestamp DESC LIMIT %s OFFSET %s
        """, params + [limit, offset])
        rows = cursor.fetchall()

    entries = []
    for r in rows:
        d = dict(r)
        d["timestamp"] = str(d["timestamp"])
        d["created_at"] = str(d["created_at"])
        # ensure content is fully excluded if requested out of schema, but we pass it currently
        entries.append(d)

    return {"interactions": entries, "total": total}


@router.patch("/interactions/{id}", response_model=InteractionResponse, tags=["🔄 Interactions"])
async def update_interaction(
    id: str,
    update: InteractionUpdate,
    agent: dict = Depends(verify_agent_key)
):
    updates, params = [], []
    for k, v in update.model_dump(exclude_unset=True).items():
        updates.append(f"{k} = %s")
        params.append(v)
    if not updates:
        raise HTTPException(400, "No fields to update")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE interactions SET {', '.join(updates)} WHERE id = %s RETURNING *", params + [id])
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Interaction not found")
        
        if update.status == "done":
            # Clear ephemeral embedding if force-closed
            cursor.execute("UPDATE interactions SET embedding = NULL WHERE id = %s", (id,))
        
        d = dict(row)
        d["timestamp"] = str(d["timestamp"])
        d["created_at"] = str(d["created_at"])
        return d

@router.delete("/interactions/{id}", tags=["🔄 Interactions"])
async def delete_interaction(id: str, agent: dict = Depends(verify_agent_key)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM interactions WHERE id = %s RETURNING id", (id,))
        if not cursor.fetchone(): raise HTTPException(404, "Interaction not found")
    flush_interaction_cache(id)
    return Response(status_code=204)


@router.get("/has-context", response_model=ContextStatusResponse, tags=["🔄 Interactions"])
async def get_has_context(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    agent: dict = Depends(verify_agent_key)
):
    """Check if any memory history exists prior to pulling detailed data."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp FROM interactions WHERE primary_entity_type = %s AND primary_entity_id = %s ORDER BY timestamp DESC", (entity_type, entity_id))
        i_rows = cursor.fetchall()
        cursor.execute("SELECT id, date FROM memories WHERE primary_entity_type = %s AND primary_entity_id = %s ORDER BY date DESC", (entity_type, entity_id))
        m_rows = cursor.fetchall()
        cursor.execute("SELECT id, created_at FROM intelligence WHERE primary_entity_type = %s AND primary_entity_id = %s ORDER BY created_at DESC", (entity_type, entity_id))
        ins_rows = cursor.fetchall()
        
    i_ids = [r["id"] for r in i_rows]; m_ids = [r["id"] for r in m_rows]; ins_ids = [r["id"] for r in ins_rows]
    return ContextStatusResponse(
        has_context=bool(i_ids or m_ids or ins_ids),
        interactions_count=len(i_ids), last_interaction_date=str(i_rows[0]["timestamp"]) if i_rows else None, interactions_ids=i_ids,
        memories_count=len(m_ids), last_memory_date=str(m_rows[0]["date"]) if m_rows else None, memories_ids=m_ids,
        Intelligences_count=len(ins_ids), last_Intelligence_date=str(ins_rows[0]["created_at"]) if ins_rows else None, Intelligences_ids=ins_ids
    )


# ============================================
# TIER 1: 🧠 Memories
# ============================================

@router.post("/memories", response_model=MemoryResponse, tags=["🧠 Memories"])
async def create_memory(body: MemoryCreate, agent: dict = Depends(verify_agent_key)):
    mem_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    embedding = None
    try:
        embedding = await generate_embedding(body.content_summary)
    except Exception as e:
        logger.warning(f"Failed embedding insertion: {e}")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
            cursor.execute("""
                INSERT INTO memories (
                    id, date, primary_entity_type, primary_entity_id, interaction_ids,
                    interaction_count, content_summary, related_entities, intents, embedding, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
            """, (mem_id, body.date, body.primary_entity_type, body.primary_entity_id, body.interaction_ids,
                  body.interaction_count, body.content_summary, json.dumps(body.related_entities), body.intents, embedding, now))
        else:
            cursor.execute("""
                INSERT INTO memories (
                    id, date, primary_entity_type, primary_entity_id, interaction_ids,
                    interaction_count, content_summary, related_entities, intents, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
            """, (mem_id, body.date, body.primary_entity_type, body.primary_entity_id, body.interaction_ids,
                  body.interaction_count, body.content_summary, json.dumps(body.related_entities), body.intents, now))
        row = dict(cursor.fetchone())
        row["date"] = str(row["date"])
        row["created_at"] = str(row["created_at"])
        if isinstance(row["related_entities"], str): row["related_entities"] = json.loads(row["related_entities"])
        return row

@router.get("/memories", tags=["🧠 Memories"])
async def list_memories(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    compacted: Optional[bool] = Query(None),
    limit: int = Query(30, le=100),
    offset: int = Query(0),
    agent: dict = Depends(verify_agent_key)
):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions, params = ["primary_entity_type = %s", "primary_entity_id = %s"], [entity_type, entity_id]
        if start_date: conditions.append("date >= %s"); params.append(start_date)
        if end_date: conditions.append("date <= %s"); params.append(end_date)
        if compacted is not None: conditions.append("compacted = %s"); params.append(compacted)

        where = " AND ".join(conditions)
        cursor.execute(f"SELECT COUNT(*) as total FROM memories WHERE {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT id, seq_id, date, primary_entity_type, primary_entity_id,
                   interaction_count, content_summary, related_entities, intents, compacted, created_at
            FROM memories WHERE {where} ORDER BY date DESC LIMIT %s OFFSET %s
        """, params + [limit, offset])
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            d["date"] = str(d["date"])
            d["created_at"] = str(d["created_at"])
            if isinstance(d["related_entities"], str): d["related_entities"] = json.loads(d["related_entities"])
            rows.append(d)

    return {"memories": rows, "total": total}

@router.patch("/memories/{id}", response_model=MemoryResponse, tags=["🧠 Memories"])
async def update_memory(id: str, update: MemoryUpdate, agent: dict = Depends(verify_agent_key)):
    updates, params = [], []
    dmp = update.model_dump(exclude_unset=True)
    if "related_entities" in dmp: dmp["related_entities"] = json.dumps(dmp["related_entities"])
    
    for k, v in dmp.items():
        updates.append(f"{k} = %s")
        params.append(v)
    if not updates: raise HTTPException(400, "No fields to update")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE memories SET {', '.join(updates)} WHERE id = %s RETURNING *", params + [id])
        row = cursor.fetchone()
        if not row: raise HTTPException(404, "Memory not found")
        
        # Regenerate embedding if content changed
        if "content_summary" in dmp:
            emb = await generate_embedding(dmp["content_summary"])
            if emb: cursor.execute("UPDATE memories SET embedding = %s::vector WHERE id = %s", (emb, id))
            
        r = dict(row)
        r["date"] = str(r["date"]); r["created_at"] = str(r["created_at"])
        if isinstance(r["related_entities"], str): r["related_entities"] = json.loads(r["related_entities"])
        return r

@router.delete("/memories/{id}", tags=["🧠 Memories"])
async def delete_memory(id: str, agent: dict = Depends(verify_agent_key)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = %s RETURNING id", (id,))
        if not cursor.fetchone(): raise HTTPException(404, "Memory not found")
    return Response(status_code=204)


# ============================================
# TIER 2: 💡 intelligence
# ============================================

@router.post("/intelligence", response_model=IntelligenceResponse, tags=["💡 Intelligence"])
async def create_intelligence(body: IntelligenceCreate, agent: dict = Depends(verify_agent_key)):
    in_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    embedding = await generate_embedding(f"{body.name}. {body.summary or body.content}")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cols = "id, primary_entity_type, primary_entity_id, source_memory_ids, knowledge_type, name, content, summary, status, created_by, created_at, updated_at"
        vals = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        params = [in_id, body.primary_entity_type, body.primary_entity_id, body.source_memory_ids, body.knowledge_type, body.name, body.content, body.summary, "confirmed", agent["id"], now, now]
        if embedding:
            cols += ", embedding"
            vals = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            params.append(embedding)

        cursor.execute(f"INSERT INTO intelligence ({cols}) VALUES {vals} RETURNING *", params)
        row = dict(cursor.fetchone())
        row["created_at"] = str(row["created_at"]); row["updated_at"] = str(row["updated_at"])
        return row

@router.get("/intelligence", tags=["💡 Intelligence"])
async def list_intelligence(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    agent: dict = Depends(verify_agent_key)
):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions, params = ["primary_entity_type = %s", "primary_entity_id = %s"], [entity_type, entity_id]
        if status: conditions.append("status = %s"); params.append(status)
        if start_date: conditions.append("created_at >= %s"); params.append(start_date)
        if end_date: conditions.append("created_at <= %s"); params.append(end_date)

        where = " AND ".join(conditions)
        cursor.execute(f"SELECT COUNT(*) as total FROM intelligence WHERE {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT id, seq_id, primary_entity_type, primary_entity_id, source_memory_ids,
                   knowledge_type, name, content, summary, status, created_by, confirmed_by, confirmed_at, created_at, updated_at
            FROM intelligence WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, params + [limit, offset])
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            d["created_at"] = str(d["created_at"]); d["updated_at"] = str(d["updated_at"])
            if d.get("confirmed_at"): d["confirmed_at"] = str(d["confirmed_at"])
            rows.append(d)

    return {"intelligence": rows, "total": total}

@router.patch("/intelligence/{id}", response_model=IntelligenceResponse, tags=["💡 Intelligence"])
async def update_intelligence(id: str, update: IntelligenceUpdate, agent: dict = Depends(verify_agent_key)):
    updates, params = [], []
    for k, v in update.model_dump(exclude_unset=True).items():
        updates.append(f"{k} = %s")
        params.append(v)
    if not updates: raise HTTPException(400, "No fields to update")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE intelligence SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s RETURNING *", params + [id])
        row = cursor.fetchone()
        if not row: raise HTTPException(404, "Intelligence not found")
        
        if "name" in update.model_dump(exclude_unset=True) or "summary" in update.model_dump(exclude_unset=True) or "content" in update.model_dump(exclude_unset=True):
            emb = await generate_embedding(f"{row['name']}. {row['summary'] or row['content']}")
            if emb: cursor.execute("UPDATE intelligence SET embedding = %s::vector WHERE id = %s", (emb, id))

        r = dict(row)
        r["created_at"] = str(r["created_at"]); r["updated_at"] = str(r["updated_at"])
        if r.get("confirmed_at"): r["confirmed_at"] = str(r["confirmed_at"])
        return r

@router.delete("/intelligence/{id}", tags=["💡 Intelligence"])
async def delete_intelligence(id: str, agent: dict = Depends(verify_agent_key)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM intelligence WHERE id = %s RETURNING id", (id,))
        if not cursor.fetchone(): raise HTTPException(404, "Intelligence not found")
    return Response(status_code=204)


# ============================================
# TIER 3: 🎓 knowledge
# ============================================

@router.post("/knowledge", response_model=KnowledgeResponse, tags=["🎓 Knowledge"])
async def create_knowledge(body: KnowledgeCreate, agent: dict = Depends(verify_agent_key)):
    les_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    embedding = await generate_embedding(f"{body.name}. {body.summary or body.content}")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cols = "id, source_intelligence_ids, knowledge_type, name, content, summary, visibility, tags, created_at, updated_at"
        vals = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        params = [les_id, body.source_intelligence_ids, body.knowledge_type, body.name, body.content, body.summary, body.visibility, body.tags, now, now]
        if embedding:
            cols += ", embedding"
            vals = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            params.append(embedding)

        cursor.execute(f"INSERT INTO knowledge ({cols}) VALUES {vals} RETURNING *", params)
        row = dict(cursor.fetchone())
        row["created_at"] = str(row["created_at"]); row["updated_at"] = str(row["updated_at"])
        return row

@router.get("/knowledge", tags=["🎓 Knowledge"])
async def list_knowledge(
    entity_type: Optional[str] = Query(None),
    entity_subtype: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    knowledge_type: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    agent: dict = Depends(verify_agent_key)
):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions, params = [], []
        if knowledge_type: conditions.append("knowledge_type = %s"); params.append(knowledge_type)
        if start_date: conditions.append("created_at >= %s"); params.append(start_date)
        if end_date: conditions.append("created_at <= %s"); params.append(end_date)
        # knowledge are globally abstracted away from IDs, but if tags contained entity_type we could filter it here.
        # For now, it simply filters via metadata or tags if we implement them, otherwise it acts fully globally.

        where = " AND ".join(conditions) if conditions else "1=1"
        cursor.execute(f"SELECT COUNT(*) as total FROM knowledge WHERE {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT id, seq_id, source_intelligence_ids, knowledge_type, name, content, summary, visibility, tags, created_at, updated_at
            FROM knowledge WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, params + [limit, offset])
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            d["created_at"] = str(d["created_at"]); d["updated_at"] = str(d["updated_at"])
            rows.append(d)

    return {"knowledge": rows, "total": total}

@router.patch("/knowledge/{id}", response_model=KnowledgeResponse, tags=["🎓 Knowledge"])
async def update_knowledge(id: str, update: KnowledgeUpdate, agent: dict = Depends(verify_agent_key)):
    updates, params = [], []
    for k, v in update.model_dump(exclude_unset=True).items():
        updates.append(f"{k} = %s")
        params.append(v)
    if not updates: raise HTTPException(400, "No fields to update")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE knowledge SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s RETURNING *", params + [id])
        row = cursor.fetchone()
        if not row: raise HTTPException(404, "Knowledge not found")
        
        if "name" in update.model_dump(exclude_unset=True) or "summary" in update.model_dump(exclude_unset=True) or "content" in update.model_dump(exclude_unset=True):
            emb = await generate_embedding(f"{row['name']}. {row['summary'] or row['content']}")
            if emb: cursor.execute("UPDATE knowledge SET embedding = %s::vector WHERE id = %s", (emb, id))

        r = dict(row)
        r["created_at"] = str(r["created_at"]); r["updated_at"] = str(r["updated_at"])
        return r

@router.delete("/knowledge/{id}", tags=["🎓 Knowledge"])
async def delete_knowledge(id: str, agent: dict = Depends(verify_agent_key)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge WHERE id = %s RETURNING id", (id,))
        if not cursor.fetchone(): raise HTTPException(404, "Knowledge not found")
    return Response(status_code=204)


# ============================================
# TIER 4: 🔍 Global Search
# ============================================

@router.post("/search/semantic", response_model=SearchResponse, tags=["🔍 Global Search"])
async def search_memory_semantic(
    request: SearchRequest,
    agent: dict = Depends(verify_agent_key)
):
    """
    Fan-out semantic search across all requested memory tiers using RAG.
    Applies mathematical chronological decay dynamically.
    """
    query_embedding = await generate_embedding(request.query)
    if not query_embedding:
        return SearchResponse(results=[], total=0, query=request.query)

    results: list[SearchResult] = []
    
    if "interactions" in request.layers:
        hits = await search_interactions_by_vector(query_embedding, request.entity_id, request.entity_type, request.entity_subtype, request.start_date, request.end_date, request.limit)
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="interaction", score=float(hit.get("score", 0)), name=None, snippet=(hit.get("content_summary") or "")[:200], entity_id=hit["primary_entity_id"], entity_type=hit["primary_entity_type"], created_at=str(hit.get("created_at", ""))
            ))
            
    if "memories" in request.layers:
        hits = await search_memories_by_vector(query_embedding, request.entity_id, request.entity_type, request.entity_subtype, request.start_date, request.end_date, request.limit)
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="memory", score=float(hit.get("score", 0)), name=None, snippet=(hit.get("content_summary") or "")[:200], entity_id=hit["primary_entity_id"], entity_type=hit["primary_entity_type"], created_at=str(hit.get("created_at", ""))
            ))

    if "intelligence" in request.layers:
        hits = await search_intelligence_by_vector(query_embedding, request.entity_id, request.entity_type, request.entity_subtype, request.start_date, request.end_date, "confirmed", request.limit)
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="Intelligence", score=float(hit.get("score", 0)), name=hit.get("name"), snippet=(hit.get("summary") or "")[:200], entity_id=hit["primary_entity_id"], entity_type=hit["primary_entity_type"], created_at=str(hit.get("created_at", ""))
            ))

    if "knowledge" in request.layers:
        hits = await search_knowledge_by_vector(query_embedding, None, request.entity_type, request.entity_subtype, request.start_date, request.end_date, request.limit)
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="Knowledge", score=float(hit.get("score", 0)), name=hit.get("name"), snippet=(hit.get("summary") or "")[:200], entity_id=None, entity_type=None, created_at=str(hit.get("created_at", ""))
            ))

    results.sort(key=lambda r: r.score, reverse=True)
    paginated = results[request.offset: request.offset + request.limit]

    log_audit(agent["id"], "search_semantic", "memory", None, {"query": request.query, "layers": request.layers})
    return SearchResponse(results=paginated, total=len(results), query=request.query)

@router.post("/search/fulltext", response_model=SearchResponse, tags=["🔍 Global Search"])
async def search_memory_fulltext(
    request: SearchRequest,
    agent: dict = Depends(verify_agent_key)
):
    """
    Fan-out deterministic exact string full-text search across all requested memory tiers using Postgres websearch_to_tsquery.
    No LLMs used. Multi-lingual support via 'simple' dictionary constraints.
    """
    results: list[SearchResult] = []
    
    if "interactions" in request.layers:
        hits = await search_interactions_by_fulltext(request.query, request.entity_id, request.entity_type, request.entity_subtype, request.start_date, request.end_date, request.limit)
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="interaction", score=float(hit.get("score", 0)), name=None, snippet=(hit.get("content_summary") or "")[:200], entity_id=hit["primary_entity_id"], entity_type=hit["primary_entity_type"], created_at=str(hit.get("created_at", ""))
            ))
            
    if "memories" in request.layers:
        hits = await search_memories_by_fulltext(request.query, request.entity_id, request.entity_type, request.entity_subtype, request.start_date, request.end_date, request.limit)
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="memory", score=float(hit.get("score", 0)), name=None, snippet=(hit.get("content_summary") or "")[:200], entity_id=hit["primary_entity_id"], entity_type=hit["primary_entity_type"], created_at=str(hit.get("created_at", ""))
            ))

    if "intelligence" in request.layers:
        hits = await search_intelligence_by_fulltext(request.query, request.entity_id, request.entity_type, request.entity_subtype, request.start_date, request.end_date, "confirmed", request.limit)
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="Intelligence", score=float(hit.get("score", 0)), name=hit.get("name"), snippet=(hit.get("summary") or "")[:200], entity_id=hit["primary_entity_id"], entity_type=hit["primary_entity_type"], created_at=str(hit.get("created_at", ""))
            ))

    if "knowledge" in request.layers:
        hits = await search_knowledge_by_fulltext(request.query, None, request.entity_type, request.entity_subtype, request.start_date, request.end_date, request.limit)
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="Knowledge", score=float(hit.get("score", 0)), name=hit.get("name"), snippet=(hit.get("summary") or "")[:200], entity_id=None, entity_type=None, created_at=str(hit.get("created_at", ""))
            ))

    results.sort(key=lambda r: r.score, reverse=True)
    paginated = results[request.offset: request.offset + request.limit]

    log_audit(agent["id"], "search_fulltext", "memory", None, {"query": request.query, "layers": request.layers})
    return SearchResponse(results=paginated, total=len(results), query=request.query)

