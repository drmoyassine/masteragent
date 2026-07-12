"""
memory/agent.py — Agent-facing memory endpoints

Unified REST SDK architecture for AI Agents.
Exposes standard CRUD operations across all four memory tiers with strict entity scoping.
All endpoints use the Agent API Key validation.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from core.storage import get_memory_db_context, cache_interaction, flush_interaction_cache
from memory_models import (
    InteractionCreate, InteractionResponse, InteractionUpdate,
    BulkInteractionCreate, BulkInteractionResponse,
    MemoryCreate, MemoryUpdate, MemoryResponse,
    IntelligenceCreate, IntelligenceUpdate, IntelligenceResponse,
    KnowledgeCreate, KnowledgeUpdate, KnowledgeResponse,
    SearchRequest, SearchResponse, SearchResult,
    ContextStatusResponse, IntelligenceContextItem, KnowledgeContextItem,
)
from memory_services import (
    generate_embedding,
    get_memory_settings,
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
from memory.auth import verify_agent_key, log_audit, require_admin_or_agent
from memory.access import ensure_entity_access, ensure_record_access, grant_entity, scope_enforced
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
    grant_entity(agent["id"], body.primary_entity_type, body.primary_entity_id)

    # Return HTTP 202 Accepted instantly
    response.status_code = 202
    return InteractionResponse(
        id=interaction_id, timestamp=now, interaction_type=body.interaction_type,
        agent_id=agent["id"], agent_name=body.agent_name or agent.get("name"),
        primary_entity_type=body.primary_entity_type, primary_entity_id=body.primary_entity_id,
        primary_entity_subtype=body.primary_entity_subtype, has_attachments=body.has_attachments,
        source=body.source, status="pending", created_at=now
    )


@router.post("/interactions/bulk", response_model=BulkInteractionResponse, tags=["🔄 Interactions"], status_code=202)
async def ingest_interactions_bulk(
    body: BulkInteractionCreate,
    response: Response,
    agent: dict = Depends(verify_agent_key)
):
    """Ingest 1–100 interactions in a single request.

    Counts as one call against the per-agent rate limit (a single trace from
    an AI agent often produces 10+ rows; charging per-row would burn the quota).
    All rows are inserted in one transaction; each is enqueued individually
    for the existing processing pipeline.
    """
    if not check_rate_limit(agent["id"]):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()
    items = body.items
    ids = [str(uuid.uuid4()) for _ in items]

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        for interaction_id, item in zip(ids, items):
            cursor.execute("""
                INSERT INTO interactions (
                    id, timestamp, interaction_type, agent_id, agent_name,
                    content, primary_entity_type, primary_entity_subtype, primary_entity_id,
                    metadata, metadata_field_map, has_attachments, attachment_refs,
                    processing_errors, source, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                interaction_id, now, item.interaction_type, agent["id"], item.agent_name or agent.get("name"),
                item.content, item.primary_entity_type, item.primary_entity_subtype, item.primary_entity_id,
                json.dumps(item.metadata or {}, ensure_ascii=False), json.dumps(item.metadata_field_map or {}, ensure_ascii=False),
                item.has_attachments, json.dumps(list(item.attachment_refs or []), ensure_ascii=False),
                json.dumps({}), item.source, "pending", now
            ))

    from memory.queue import interactions_queue
    for interaction_id in ids:
        await interactions_queue.add(
            "ingest_interaction",
            {"interaction_id": interaction_id},
            {"attempts": 3, "backoff": {"type": "exponential", "delay": 2000}}
        )

    log_audit(agent["id"], "ingest_interactions_bulk", "interaction", ids[0], {
        "count": len(ids),
        "interaction_types": sorted({i.interaction_type for i in items}),
    })
    for item in items:
        grant_entity(agent["id"], item.primary_entity_type, item.primary_entity_id)

    response.status_code = 202
    return BulkInteractionResponse(ids=ids, count=len(ids), status="pending")


# ============================================
# 📄 Synchronous Document Parsing
# ============================================

class ParseDocumentRequest(BaseModel):
    """Parse a single document synchronously (vision OCR for PDFs/images).

    Provide either `url` (fetched server-side) or `data` (base64 bytes).
    `prompt` overrides the default vision extraction prompt.
    """
    url: Optional[str] = None
    data: Optional[str] = None  # base64-encoded file bytes (alternative to url)
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    prompt: Optional[str] = None


@router.post("/parse-document", tags=["🔄 Interactions"])
async def parse_document_sync(
    body: ParseDocumentRequest,
    agent: dict = Depends(verify_agent_key),
):
    """Fetch a document by URL (or decode inline base64) and extract its text via
    the same vision pipeline used during interaction ingestion. Returns the parsed
    text synchronously so callers (e.g. n8n) don't have to wait on the async worker.
    """
    if not check_rate_limit(agent["id"]):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if not body.url and not body.data:
        raise HTTPException(status_code=422, detail="Provide either 'url' or 'data'.")

    # 1. Resolve raw bytes
    raw_blob: Optional[bytes] = None
    if body.data:
        import base64
        try:
            raw_blob = base64.b64decode(body.data, validate=True)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid base64 in 'data'.")
        max_bytes = int(os.environ.get("MAX_DOCUMENT_BYTES", str(25 * 1024 * 1024)))
        if len(raw_blob) > max_bytes:
            raise HTTPException(status_code=413, detail="Document exceeds the configured size limit")
    else:
        from core.url_security import fetch_document, UnsafeURL
        try:
            raw_blob = await fetch_document(body.url)
        except UnsafeURL as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch document URL: {e}")

    if not raw_blob:
        raise HTTPException(status_code=422, detail="Document is empty.")

    # 2. Infer mime/filename (mirror the ingestion worker)
    import filetype
    inferred_mime = None
    kind = filetype.guess(raw_blob)
    if kind:
        inferred_mime = kind.mime
    mime_type = inferred_mime or body.mime_type or "application/octet-stream"
    filename = body.filename or (body.url.split("/")[-1] if body.url else "attachment")

    # 3. Parse
    try:
        parsed = await parse_document(raw_blob, filename, mime_type, prompt=body.prompt)
    except Exception as e:
        logger.error(f"parse-document failed for {filename} ({mime_type}): {e}")
        raise HTTPException(status_code=500, detail=f"Parsing failed: {e}")

    text = parsed.get("text") or ""
    log_audit(agent["id"], "parse_document", "document", filename, {
        "mime_type": mime_type,
        "chars": len(text),
        "via": "url" if body.url else "data",
    })

    return {
        "text": text,
        "pages": parsed.get("pages", 0),
        "has_images": parsed.get("has_images", False),
        "mime_type": mime_type,
        "filename": filename,
    }


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
    ensure_entity_access(agent, entity_type, entity_id)
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
    ensure_record_access(agent, "interactions", id)
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
    ensure_record_access(agent, "interactions", id)
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
    summary_only: bool = Query(
        False,
        description="Return only counts and has_context. Use this for pre-checks; it avoids loading historical IDs and records.",
    ),
    agent: dict = Depends(verify_agent_key)
):
    """Check if any memory history exists prior to pulling detailed data."""
    ensure_entity_access(agent, entity_type, entity_id)
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if summary_only:
            cursor.execute("""
                SELECT COUNT(*) AS count, MAX(timestamp) AS last_date
                FROM interactions
                WHERE primary_entity_type=%s AND primary_entity_id=%s
                  AND status IN ('pending', 'failed')
                  AND interaction_type NOT IN ('internal_ai_tool_call', 'internal_ai_thought')
            """, (entity_type, entity_id))
            i_summary = cursor.fetchone() or {}
            cursor.execute("""
                SELECT COUNT(*) AS count, MAX(date) AS last_date
                FROM memories WHERE primary_entity_type=%s AND primary_entity_id=%s
            """, (entity_type, entity_id))
            m_summary = cursor.fetchone() or {}
            cursor.execute("""
                SELECT COUNT(*) AS count, MAX(created_at) AS last_date
                FROM intelligence WHERE primary_entity_type=%s AND primary_entity_id=%s
            """, (entity_type, entity_id))
            ins_summary = cursor.fetchone() or {}
            i_count = int(i_summary.get("count") or 0)
            m_count = int(m_summary.get("count") or 0)
            ins_count = int(ins_summary.get("count") or 0)
            return ContextStatusResponse(
                has_context=bool(i_count or m_count or ins_count),
                interactions_count=i_count,
                last_interaction_date=str(i_summary["last_date"]) if i_summary.get("last_date") else None,
                interactions_ids=[],
                memories_count=m_count,
                last_memory_date=str(m_summary["last_date"]) if m_summary.get("last_date") else None,
                memories_ids=[],
                Intelligences_count=ins_count,
                last_Intelligence_date=str(ins_summary["last_date"]) if ins_summary.get("last_date") else None,
                Intelligences_ids=[],
                intelligences=[], knowledge_count=0, knowledge=[],
            )
        cursor.execute("""
            SELECT id, timestamp FROM interactions
            WHERE primary_entity_type = %s AND primary_entity_id = %s
              AND status IN ('pending', 'failed')
              AND interaction_type NOT IN ('internal_ai_tool_call', 'internal_ai_thought')
            ORDER BY timestamp DESC
        """, (entity_type, entity_id))
        i_rows = cursor.fetchall()
        cursor.execute("SELECT id, date FROM memories WHERE primary_entity_type = %s AND primary_entity_id = %s ORDER BY date DESC", (entity_type, entity_id))
        m_rows = cursor.fetchall()
        cursor.execute(
            "SELECT id, name, summary, status, signals, created_at FROM intelligence WHERE primary_entity_type = %s AND primary_entity_id = %s ORDER BY created_at DESC",
            (entity_type, entity_id)
        )
        ins_rows = cursor.fetchall()
        cursor.execute("SELECT id, name, summary, visibility, created_at, category, metadata, quality_score, merge_count FROM knowledge WHERE status = 'active' AND (visibility = 'shared' OR visibility IS NULL) ORDER BY quality_score DESC NULLS LAST, created_at DESC LIMIT 30")
        k_rows = cursor.fetchall()

    i_ids = [r["id"] for r in i_rows]
    m_ids = [r["id"] for r in m_rows]
    ins_ids = [r["id"] for r in ins_rows]
    intelligences = [
        IntelligenceContextItem(
            id=r["id"], name=r["name"] or "", summary=r.get("summary"),
            status=r["status"], signals=r.get("signals") or [],
            created_at=str(r["created_at"])
        ) for r in ins_rows
    ]
    knowledge_items = [
        KnowledgeContextItem(
            id=r["id"], name=r["name"] or "", summary=r.get("summary"),
            visibility=r.get("visibility"), created_at=str(r["created_at"]),
            category=r.get("category"), metadata=r.get("metadata"),
            quality_score=r.get("quality_score"), merge_count=r.get("merge_count", 0),
        ) for r in k_rows
    ]
    return ContextStatusResponse(
        has_context=bool(i_ids or m_ids or ins_ids),
        interactions_count=len(i_ids), last_interaction_date=str(i_rows[0]["timestamp"]) if i_rows else None, interactions_ids=i_ids,
        memories_count=len(m_ids), last_memory_date=str(m_rows[0]["date"]) if m_rows else None, memories_ids=m_ids,
        Intelligences_count=len(ins_ids), last_Intelligence_date=str(ins_rows[0]["created_at"]) if ins_rows else None, Intelligences_ids=ins_ids,
        intelligences=intelligences,
        knowledge_count=len(knowledge_items), knowledge=knowledge_items,
    )


@router.get("/get-context", tags=["🔄 Interactions"])
async def get_context(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    interaction_types: Optional[str] = Query(
        None,
        description=(
            "Optional comma-separated list of interaction_type values. "
            "Behaviour depends on interaction_types_mode. Empty/null = all."
        ),
    ),
    interaction_types_mode: Optional[str] = Query(
        "include",
        description=(
            '"include" = only return listed types; '
            '"exclude" = return all EXCEPT listed types. '
            "Only effective when interaction_types is set."
        ),
    ),
    interaction_limit: Optional[int] = Query(
        200, ge=1, le=1000,
        description="Cap on returned interactions, taking the most recent records first. Pass a higher value explicitly when needed.",
    ),
    memory_limit: Optional[int] = Query(
        100, ge=1, le=1000,
        description="Cap on returned memories, taking the most recent records first. Pass a higher value explicitly when needed.",
    ),
    intelligence_limit: Optional[int] = Query(
        100, ge=1, le=1000,
        description="Cap on returned intelligence, taking the most recent records first. Pass a higher value explicitly when needed.",
    ),
    knowledge_facets: Optional[str] = Query(
        None,
        description=(
            'JSON object of governed facets to HARD-filter knowledge on, e.g. '
            '{"country":"Malaysia"}. When omitted, facets are derived from the '
            "entity's CRM profile (profile_facet_map). Filter applies to all "
            "knowledge categories; the always-on management skill is exempt."
        ),
    ),
    knowledge_category: Optional[str] = Query(
        None, description="Restrict knowledge to one category (skill|playbook|best_practices|lessons_learned|trade_knowledge)."
    ),
    agent: dict = Depends(verify_agent_key)
):
    """Return full context for an entity: uncompacted interactions
    (pending/failed, excluding telemetry), all memories, and all intelligence. Payload shape matches
    the outbound webhook so agents can request the same context on demand.

    Optional ?interaction_types=a,b&interaction_types_mode=include|exclude
    filters the interactions list (memories and intelligence are unaffected)."""
    ensure_entity_access(agent, entity_type, entity_id)
    type_filter: Optional[List[str]] = None
    if interaction_types:
        type_filter = [t.strip() for t in interaction_types.split(",") if t.strip()]
        if not type_filter:
            type_filter = None

    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        # “Uncompacted” means not yet successfully processed into a memory.
        # Failed rows remain eligible for retry. Completed historical rows are
        # deliberately excluded; callers should use the memories collection for
        # their compacted representation.
        interactions_query = f"""
            SELECT id, interaction_type, content, metadata, timestamp, source, is_enriched
            FROM interactions
            WHERE primary_entity_type = %s AND primary_entity_id = %s
              AND status IN ('pending', 'failed')
        """
        interactions_params: list = [entity_type, entity_id]
        if type_filter:
            if interaction_types_mode == "exclude":
                interactions_query += " AND interaction_type != ALL(%s)"
            else:
                interactions_query += " AND interaction_type = ANY(%s)"
            interactions_params.append(type_filter)
        else:
            # Telemetry is a producer input for reflection, not user/entity
            # context. Keep it out unless a caller explicitly asks for it.
            interactions_query += " AND interaction_type NOT IN ('internal_ai_tool_call', 'internal_ai_thought')"
        interactions_query += " ORDER BY timestamp DESC"
        if interaction_limit:
            interactions_query += " LIMIT %s"
            interactions_params.append(interaction_limit)
        cursor.execute(interactions_query, interactions_params)
        interaction_rows = cursor.fetchall()
        if interaction_limit:
            interaction_rows = list(reversed(interaction_rows))
        interactions = [{
            "id": r["id"],
            "interaction_type": r["interaction_type"],
            "content": r["content"],
            "metadata": r["metadata"],
            "timestamp": str(r["timestamp"]),
            "source": r["source"],
            "is_enriched": r["is_enriched"],
        } for r in interaction_rows]

        cursor.execute(f"""
            SELECT id, signals, name, content, summary, status, created_at
            FROM intelligence
            WHERE primary_entity_type = %s AND primary_entity_id = %s
            ORDER BY created_at DESC
            {"LIMIT %s" if intelligence_limit else ""}
        """, (entity_type, entity_id) + ((intelligence_limit,) if intelligence_limit else ()))
        intelligence_rows = cursor.fetchall()
        if intelligence_limit:
            intelligence_rows = list(reversed(intelligence_rows))
        intelligence = [{
            "id": r["id"],
            "signals": r["signals"] or [],
            "name": r["name"],
            "content": r["content"],
            "summary": r["summary"],
            "status": r["status"],
            "created_at": str(r["created_at"]),
        } for r in intelligence_rows]

        cursor.execute(f"""
            SELECT id, date, content_summary, related_entities, intents, compacted
            FROM memories
            WHERE primary_entity_type = %s AND primary_entity_id = %s
            ORDER BY date DESC
            {"LIMIT %s" if memory_limit else ""}
        """, (entity_type, entity_id) + ((memory_limit,) if memory_limit else ()))
        memory_rows = cursor.fetchall()
        if memory_limit:
            memory_rows = list(reversed(memory_rows))
        memories = [{
            "id": r["id"],
            "date": str(r["date"]),
            "content_summary": r["content_summary"],
            "related_entities": r["related_entities"],
            "intents": r["intents"],
            "compacted": r["compacted"],
        } for r in memory_rows]

        # Knowledge (all categories: declarative + playbooks + skills).
        # Sprint 2.5: governed facet hard-filter (WS-5), pinned always-on
        # management skill exempt from the filter (WS-3), and a lean index mode
        # that drops full content so the orchestrator pulls records on demand (WS-1).
        # Relevance ranking + cap + fallback query preserved from Sprint 2.
        settings = get_memory_settings() or {}
        k_count = int(settings.get("context_knowledge_count") or 30)
        k_floor = float(settings.get("context_knowledge_min_similarity") or 0.0)

        # Resolve governed facets: explicit param → else derive from CRM profile.
        from memory_facets import canonicalize_facets
        resolved_facets: dict = {}
        facets_from_profile = False
        if knowledge_facets:
            try:
                resolved_facets = json.loads(knowledge_facets) or {}
            except Exception:
                resolved_facets = {}
        if not resolved_facets:
            try:
                from memory_facets import get_profile_facet_map
                pmap = get_profile_facet_map() or {}
                if pmap:
                    cursor.execute(
                        "SELECT properties FROM entity_profiles WHERE entity_type = %s AND entity_id = %s",
                        (entity_type, entity_id),
                    )
                    prow = cursor.fetchone()
                    props = (prow["properties"] if prow else {}) or {}
                    if isinstance(props, str):
                        props = json.loads(props)
                    for facet_key, prop_key in pmap.items():
                        v = props.get(prop_key) if isinstance(props, dict) else None
                        if v:
                            resolved_facets[facet_key] = str(v)
                    facets_from_profile = True
            except Exception as e:
                logger.warning(f"Facet derivation from profile failed: {e}")
                resolved_facets = {}
        # Keep only non-empty facet values
        resolved_facets = {k: v for k, v in resolved_facets.items() if v}
        # Canonicalize to stored casing/spelling so exact JSONB containment does
        # not silently miss (e.g. CRM 'malaysia' vs stored 'Malaysia'). For
        # profile-derived facets, drop values that exist nowhere rather than
        # hard-filtering to zero results on a value the corpus has never seen.
        # Profile-derived facets only affect the bounded in-memory ranking
        # below; they are never SQL filters. Do not scan the entire Knowledge
        # table to canonicalize them on every context request. Explicit facet
        # filters retain canonicalization because they use JSONB containment.
        if resolved_facets and not facets_from_profile:
            try:
                resolved_facets = canonicalize_facets(cursor, resolved_facets, drop_unmatched=facets_from_profile)
            except Exception as e:
                logger.warning(f"Facet canonicalization failed: {e}")
        facet_clause = ""
        facet_params: list = []
        if resolved_facets and not facets_from_profile:
            facet_clause = " AND metadata @> %s::jsonb"
            facet_params.append(json.dumps({"facets": resolved_facets}))
        category_clause = " AND category = %s" if knowledge_category else ""
        category_params = [knowledge_category] if knowledge_category else []

        # WS-3: pinned always-on management skill(s) — exempt from filter + cap.
        pinned_clause = " AND metadata->>'always_inject' = 'true'"
        cursor.execute(f"""
            SELECT id, name, category, signals, content, summary, tags, metadata, quality_score, merge_count
            FROM knowledge
            WHERE status = 'active' AND (visibility = 'shared' OR visibility IS NULL)
            {pinned_clause}
            ORDER BY created_at ASC
        """)
        pinned_rows = cursor.fetchall()

        # WS-5: the rest, with facet hard-filter + optional category, relevance-ranked.
        knowledge_rows = None
        not_pinned = " AND metadata->>'always_inject' IS DISTINCT FROM 'true'"
        try:
            cursor.execute(f"""
                WITH qv AS (
                    SELECT AVG(embedding) AS v FROM (
                        SELECT embedding FROM interactions
                        WHERE primary_entity_type = %s AND primary_entity_id = %s
                          AND embedding IS NOT NULL
                        ORDER BY timestamp DESC LIMIT 10
                    ) t
                )
                SELECT k.id, k.name, k.category, k.signals, k.content, k.summary,
                       k.tags, k.metadata, k.quality_score, k.merge_count,
                       CASE WHEN qv.v IS NOT NULL AND k.embedding IS NOT NULL
                            THEN 1 - (k.embedding <=> qv.v) ELSE NULL END AS relevance
                FROM knowledge k, qv
                WHERE k.status = 'active'
                  AND (k.visibility = 'shared' OR k.visibility IS NULL)
                  {not_pinned}{facet_clause}{category_clause}
                  AND (
                        %s <= 0
                        OR (qv.v IS NOT NULL AND k.embedding IS NOT NULL
                            AND (1 - (k.embedding <=> qv.v)) >= %s)
                      )
                ORDER BY
                    CASE WHEN qv.v IS NOT NULL AND k.embedding IS NOT NULL
                         THEN (1 - (k.embedding <=> qv.v)) * 0.7 + COALESCE(k.quality_score, 0) * 0.3
                         ELSE COALESCE(k.quality_score, 0) END DESC,
                    k.created_at DESC
                LIMIT %s
            """, (entity_type, entity_id) + tuple(facet_params) + tuple(category_params) +
                 (k_floor, k_floor, max(k_count * 3, k_count)))
            knowledge_rows = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Relevance-ranked knowledge query failed, falling back to quality order: {e}")
            if k_floor > 0:
                knowledge_rows = []
            else:
                cursor.execute(f"""
                    SELECT id, name, category, signals, content, summary, tags, metadata, quality_score, merge_count
                    FROM knowledge
                    WHERE status = 'active' AND (visibility = 'shared' OR visibility IS NULL)
                    {not_pinned}{facet_clause}{category_clause}
                    ORDER BY quality_score DESC NULLS LAST, created_at DESC
                    LIMIT %s
                """, tuple(facet_params) + tuple(category_params) + (k_count,))
                knowledge_rows = cursor.fetchall()

        def _facets_of(r):
            md = r["metadata"] or {}
            if isinstance(md, str):
                try: md = json.loads(md)
                except Exception: md = {}
            return md.get("facets") or {}

        def _full_item(r):
            return {
                "id": r["id"], "name": r["name"], "category": r["category"],
                "signals": r["signals"] or [], "content": r["content"], "summary": r["summary"],
                "tags": r["tags"], "metadata": r["metadata"],
                "quality_score": r["quality_score"], "merge_count": r["merge_count"],
            }

        def _index_item(r):
            # Lean index: no content, no heavy metadata, no tags. facets included for decisions.
            return {
                "id": r["id"], "name": r["name"], "category": r["category"],
                "signals": r["signals"] or [], "summary": r["summary"], "facets": _facets_of(r),
            }

        # Profile-derived facets are a bounded boost, never a hard filter. Explicit
        # request facets were already applied as deterministic SQL filters above.
        if facets_from_profile and resolved_facets:
            def _rank(row):
                facets = {str(k): str(v).lower() for k, v in _facets_of(row).items()}
                matched = sum(
                    1 for key, value in resolved_facets.items()
                    if facets.get(str(key), "") == str(value).lower()
                )
                profile_match = matched / max(len(resolved_facets), 1)
                relevance = float(row.get("relevance") or 0.0)
                quality = float(row.get("quality_score") or 0.0)
                return 0.65 * relevance + 0.20 * quality + 0.15 * profile_match
            knowledge_rows = sorted(knowledge_rows, key=_rank, reverse=True)[:k_count]
        else:
            knowledge_rows = list(knowledge_rows)[:k_count]

        # Always-on records are fully injected. Every retrieved ordinary record
        # is index-only and must be pulled explicitly before use.
        knowledge = [_full_item(r) for r in pinned_rows]
        knowledge += [_index_item(r) for r in knowledge_rows]

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "interactions": interactions,
        "intelligence": intelligence,
        "memories": memories,
        "knowledge": knowledge,
    }


# ============================================
# TIER 1: 🧠 Memories
# ============================================

@router.post("/memories", response_model=MemoryResponse, tags=["🧠 Memories"])
async def create_memory(body: MemoryCreate, agent: dict = Depends(verify_agent_key)):
    grant_entity(agent["id"], body.primary_entity_type, body.primary_entity_id)
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
    ensure_entity_access(agent, entity_type, entity_id)
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
    ensure_record_access(agent, "memories", id)
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
    ensure_record_access(agent, "memories", id)
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
    grant_entity(agent["id"], body.primary_entity_type, body.primary_entity_id)
    in_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    embedding = await generate_embedding(f"{body.name}. {body.summary or body.content}")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cols = "id, primary_entity_type, primary_entity_id, source_memory_ids, signals, name, content, summary, status, created_by, created_at, updated_at"
        vals = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        params = [in_id, body.primary_entity_type, body.primary_entity_id, body.source_memory_ids, body.signals or [], body.name, body.content, body.summary, "confirmed", agent["id"], now, now]
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
    ensure_entity_access(agent, entity_type, entity_id)
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
                   signals, name, content, summary, status, created_by, confirmed_by, confirmed_at, created_at, updated_at
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
    ensure_record_access(agent, "intelligence", id)
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
    ensure_record_access(agent, "intelligence", id)
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
    """Create a knowledge record. Routes through insert_knowledge so category,
    metadata, status, SKILL.md rendering (skill/playbook) and governed facet
    extraction are applied consistently with every other creation pathway."""
    from memory_db_writes import insert_knowledge
    from memory_facets import enrich_metadata_with_facets

    knowledge_id = str(uuid.uuid4())
    category = body.category or "trade_knowledge"
    embedding = await generate_embedding(f"{body.name}. {body.summary or body.content}")
    metadata = await enrich_metadata_with_facets(body.metadata, body.name, body.content, body.summary or "")
    metadata = dict(metadata or {})
    metadata["created_by_agent_id"] = agent["id"]

    insert_knowledge(
        knowledge_id=knowledge_id,
        intelligence_ids=body.source_Intelligence_ids or [],
        signals=body.signals or [],
        category=category,
        name=body.name,
        content=body.content,
        summary=body.summary,
        embedding=embedding,
        tags=body.tags or [],
        visibility=body.visibility or "shared",
        metadata=metadata,
        source_pathway="agent_created",
        status=body.status or "draft",
    )

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge WHERE id = %s", (knowledge_id,))
        row = dict(cursor.fetchone())
        row["created_at"] = str(row["created_at"]); row["updated_at"] = str(row["updated_at"])
        return row

@router.get("/knowledge", tags=["🎓 Knowledge"])
async def list_knowledge(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    signal: Optional[str] = Query(None),
    category: Optional[str] = Query(None, description="skill | playbook | best_practices | lessons_learned | trade_knowledge"),
    facets: Optional[str] = Query(None, description='JSON object of governed facets, e.g. {"country":"Malaysia"}'),
    strict: bool = Query(False, description="True = hard-filter on facets; False (default) = ignore facets"),
    status: str = Query("active", description="Agent-facing knowledge is always active-only"),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    agent: dict = Depends(verify_agent_key)
):
    """List knowledge records. Knowledge is global (not entity-scoped), so
    filtering is by category/signal/date and governed facets only. Retired and
    draft records are administrator history, not agent-facing knowledge."""
    if status != "active":
        raise HTTPException(status_code=400, detail="Agent knowledge endpoints only expose active records")
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        conditions, params = ["visibility = 'shared'", "status = 'active'"], []
        if category:
            conditions.append("category = %s"); params.append(category)
        if signal:
            conditions.append("%s = ANY(signals)"); params.append(signal)
        if start_date:
            conditions.append("created_at >= %s"); params.append(start_date)
        if end_date:
            conditions.append("created_at <= %s"); params.append(end_date)
        if strict and facets:
            try:
                facets_obj = json.loads(facets)
                if facets_obj:
                    conditions.append("metadata @> %s::jsonb")
                    params.append(json.dumps({"facets": facets_obj}))
            except Exception:
                pass

        where = " AND ".join(conditions)
        cursor.execute(f"SELECT COUNT(*) as total FROM knowledge WHERE {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT id, seq_id, source_intelligence_ids, signals, name, content, summary,
                   visibility, tags, category, metadata, quality_score, merge_count, version, created_at, updated_at
            FROM knowledge WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, params + [limit, offset])
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            d["created_at"] = str(d["created_at"]); d["updated_at"] = str(d["updated_at"])
            rows.append(d)

    return {"knowledge": rows, "total": total}


@router.get("/knowledge/facets", tags=["🎓 Knowledge"])
async def list_knowledge_facets(
    key: Optional[str] = Query(None, description="Return distinct values for a single facet key only"),
    agent: dict = Depends(require_admin_or_agent)
):
    """Discover the governed facet vocabulary in use across active knowledge.
    No key → {facet_key: [distinct values...]} for every schema key with values.
    ?key=country → ["Malaysia", "United Kingdom", ...]. Values come from metadata.facets."""
    from memory_facets import get_facets_schema
    schema = get_facets_schema()
    schema_keys = [s.get("key") for s in schema if s.get("key")]
    keys = [key] if key else schema_keys
    out: dict = {}
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        for k in keys:
            if not k:
                continue
            cursor.execute("""
                SELECT DISTINCT metadata->'facets'->>%s AS v
                FROM knowledge
                WHERE status = 'active'
                  AND (visibility = 'shared' OR visibility IS NULL)
                  AND metadata ? 'facets'
                  AND metadata->'facets' ? %s
            """, (k, k))
            vals = []
            for row in cursor.fetchall():
                v = row["v"]
                if v:
                    vals.append(v)
            out[k] = sorted(set(vals))
    if key:
        return out.get(key, [])
    return out


@router.get("/knowledge/{id}", tags=["🎓 Knowledge"])
async def get_knowledge(id: str, agent: dict = Depends(verify_agent_key)):
    """Retrieve a single full knowledge record (on-demand pull after the agent
    scans the lean index from get-context). Returns content (SKILL.md for
    skill/playbook), metadata, signals, quality, version."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, source_intelligence_ids, signals, name, content, summary,
                   visibility, tags, category, metadata, quality_score, merge_count,
                   version, status, created_at, updated_at
            FROM knowledge
            WHERE id = %s AND status = 'active' AND (visibility = 'shared' OR visibility IS NULL)
        """, (id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Knowledge not found")
        d = dict(row)
        d["created_at"] = str(d["created_at"]); d["updated_at"] = str(d["updated_at"])
        return d

def _assert_agent_mutable(cursor, id: str, agent: dict) -> None:
    """Block agent-key mutations of system-governed knowledge (the always-on
    management skill and other source_pathway='system' records). These govern
    every agent globally, so a single agent key must not be able to alter or
    delete them — that's an admin-only operation."""
    cursor.execute(
        "SELECT source_pathway, metadata->>'always_inject' AS ai, "
        "metadata->>'created_by_agent_id' AS owner, merged_into, merged_from, "
        "consolidation_event_id FROM knowledge WHERE id = %s",
        (id,),
    )
    r = cursor.fetchone()
    if r and (r.get("source_pathway") == "system" or r.get("ai") == "true"):
        raise HTTPException(403, "This knowledge record is system-governed and can only be modified by an admin")
    if r and (r.get("merged_into") or r.get("merged_from") or r.get("consolidation_event_id")):
        raise HTTPException(409, "Consolidated knowledge is admin-governed; reverse the consolidation before mutation")
    if scope_enforced() and r and r.get("owner") != agent.get("id") and agent.get("id") != "mcp-service":
        raise HTTPException(403, "Agent can only modify knowledge it created")


@router.patch("/knowledge/{id}", response_model=KnowledgeResponse, tags=["🎓 Knowledge"])
async def update_knowledge(id: str, update: KnowledgeUpdate, agent: dict = Depends(verify_agent_key)):
    updates, params = [], []
    for k, v in update.model_dump(exclude_unset=True).items():
        # metadata is a JSONB column — serialize dicts so psycopg binds them correctly.
        if k == "metadata" and v is not None:
            import json as _json
            v = _json.dumps(v)
        updates.append(f"{k} = %s")
        params.append(v)
    if not updates: raise HTTPException(400, "No fields to update")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        _assert_agent_mutable(cursor, id, agent)
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
        _assert_agent_mutable(cursor, id, agent)
        cursor.execute("DELETE FROM knowledge WHERE id = %s RETURNING id", (id,))
        if not cursor.fetchone(): raise HTTPException(404, "Knowledge not found")
    return Response(status_code=204)


# ============================================
# TIER 4: 🔍 Global Search
# ============================================

@router.post("/search/semantic", response_model=SearchResponse, tags=["🔍 Global Search"])
@router.post("/search", response_model=SearchResponse, include_in_schema=False)
async def search_memory_semantic(
    request: SearchRequest,
    agent: dict = Depends(verify_agent_key)
):
    """
    Fan-out semantic search across all requested memory tiers using RAG.
    Applies mathematical chronological decay dynamically.
    """
    non_global_layers = [layer for layer in request.layers if layer != "knowledge"]
    if scope_enforced() and non_global_layers:
        if not request.entity_type or not request.entity_id:
            raise HTTPException(403, "Scoped searches require entity_type and entity_id")
        ensure_entity_access(agent, request.entity_type, request.entity_id)
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
        hits = await search_knowledge_by_vector(
            query_embedding, request.knowledge_signal, request.entity_type, request.entity_subtype,
            request.start_date, request.end_date, request.limit, category=request.knowledge_category,
            facets=request.knowledge_facets, strict=bool(request.strict),
        )
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
    non_global_layers = [layer for layer in request.layers if layer != "knowledge"]
    if scope_enforced() and non_global_layers:
        if not request.entity_type or not request.entity_id:
            raise HTTPException(403, "Scoped searches require entity_type and entity_id")
        ensure_entity_access(agent, request.entity_type, request.entity_id)
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
        hits = await search_knowledge_by_fulltext(
            request.query, request.knowledge_signal, request.entity_type, request.entity_subtype,
            request.start_date, request.end_date, request.limit, category=request.knowledge_category,
            facets=request.knowledge_facets, strict=bool(request.strict),
        )
        for hit in hits:
            results.append(SearchResult(
                id=hit["id"], layer="Knowledge", score=float(hit.get("score", 0)), name=hit.get("name"), snippet=(hit.get("summary") or "")[:200], entity_id=None, entity_type=None, created_at=str(hit.get("created_at", ""))
            ))

    results.sort(key=lambda r: r.score, reverse=True)
    paginated = results[request.offset: request.offset + request.limit]

    log_audit(agent["id"], "search_fulltext", "memory", None, {"query": request.query, "layers": request.layers})
    return SearchResponse(results=paginated, total=len(results), query=request.query)

