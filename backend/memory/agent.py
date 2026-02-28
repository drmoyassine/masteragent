"""
memory/agent.py — Agent interaction endpoints

Handles memory ingestion, semantic search, lessons, and interaction timeline for agents.
Auth: API Key (`verify_agent_key`)
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException

from memory_db import get_memory_db_context
from memory_models import (
    InteractionResponse, LessonCreate, LessonResponse, LessonUpdate,
    SearchRequest, SearchResponse, SearchResult, TimelineEntry, RelatedEntity
)
from memory_services import (
    chunk_text, extract_entities, generate_embedding, generate_embeddings_batch,
    get_memory_settings, init_qdrant_collections, parse_document, scrub_pii,
    search_vectors, summarize_text, upsert_vector
)
from memory.auth import verify_agent_key, log_audit
from memory_tasks import check_rate_limit

router = APIRouter()


# ============================================
# Agent API - Interactions (Ingest)
# ============================================

@router.post("/interactions", response_model=InteractionResponse)
async def ingest_interaction(
    text: str = Form(...),
    channel: str = Form(...),
    entities: str = Form("[]"),
    metadata: str = Form("{}"),
    files: List[UploadFile] = File(default=[]),
    agent: dict = Depends(verify_agent_key)
):
    if not check_rate_limit(agent["id"]):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    now = datetime.now(timezone.utc).isoformat()
    memory_id = str(uuid.uuid4())
    
    entities_list = json.loads(entities) if entities else []
    metadata_dict = json.loads(metadata) if metadata else {}
    settings = get_memory_settings()
    
    parsed_docs = []
    all_text = text
    for file in files:
        content = await file.read()
        parsed = await parse_document(content, file.filename, file.content_type)
        doc_id = str(uuid.uuid4())
        parsed_docs.append({
            "id": doc_id, "filename": file.filename, "file_type": file.content_type,
            "file_size": len(content), "parsed_text": parsed["text"]
        })
        if parsed["text"]:
            all_text += f"\n\n---\n[Document: {file.filename}]\n{parsed['text']}"
    
    summary = await summarize_text(all_text)
    if not entities_list:
        entities_list = await extract_entities(all_text)
    
    chunks = chunk_text(all_text, chunk_size=settings.get("chunk_size", 400), chunk_overlap=settings.get("chunk_overlap", 80))
    embeddings = await generate_embeddings_batch(chunks) if chunks else []
    
    pii_scrubbed_text, pii_scrubbed_summary, scrubbed_chunks, scrubbed_embeddings = None, None, [], []
    if settings.get("pii_scrubbing_enabled", False):
        pii_scrubbed_text = await scrub_pii(all_text)
        pii_scrubbed_summary = await scrub_pii(summary) if summary else ""
        scrubbed_chunks = chunk_text(pii_scrubbed_text, chunk_size=settings.get("chunk_size", 400), chunk_overlap=settings.get("chunk_overlap", 80))
        scrubbed_embeddings = await generate_embeddings_batch(scrubbed_chunks) if scrubbed_chunks else []
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memories (id, timestamp, channel, raw_text, summary_text, has_documents, is_shared, entities_json, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """, (memory_id, now, channel, text, summary, 1 if parsed_docs else 0, json.dumps(entities_list), json.dumps(metadata_dict), now, now))
        
        for doc in parsed_docs:
            cursor.execute("INSERT INTO memory_documents (id, memory_id, filename, file_type, file_size, parsed_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (doc["id"], memory_id, doc["filename"], doc["file_type"], doc["file_size"], doc["parsed_text"], now))
        
        if settings.get("pii_scrubbing_enabled") and settings.get("auto_share_scrubbed"):
            shared_memory_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO memories_shared (id, original_memory_id, timestamp, channel, scrubbed_text, summary_text, has_documents, entities_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (shared_memory_id, memory_id, now, channel, pii_scrubbed_text, pii_scrubbed_summary, 1 if parsed_docs else 0, json.dumps(entities_list), json.dumps(metadata_dict), now))
            for i, (chunk, embedding) in enumerate(zip(scrubbed_chunks, scrubbed_embeddings)):
                if embedding:
                    await upsert_vector("memory_shared", f"{shared_memory_id}_{i}", embedding, {
                        "memory_id": shared_memory_id, "original_memory_id": memory_id, "chunk_index": i, "channel": channel,
                        "timestamp": now, "entities": entities_list, "is_shared": True
                    })
    
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        if embedding:
            await upsert_vector("memory_interactions", f"{memory_id}_{i}", embedding, {
                "memory_id": memory_id, "chunk_index": i, "channel": channel,
                "timestamp": now, "entities": entities_list, "is_shared": False
            })
    
    log_audit(agent["id"], "ingest_interaction", "memory", memory_id, {"channel": channel})
    return InteractionResponse(
        id=memory_id, timestamp=now, channel=channel, summary_text=summary, has_documents=bool(parsed_docs),
        entities=[RelatedEntity(**e) for e in entities_list], metadata=metadata_dict
    )


# ============================================
# Agent API - Search
# ============================================

@router.post("/search", response_model=SearchResponse)
async def search_memories(request: SearchRequest, agent: dict = Depends(verify_agent_key)):
    query_embedding = await generate_embedding(request.query)
    if not query_embedding:
        return SearchResponse(results=[], total=0, query=request.query)
    
    results = []
    qdrant_filter = {}
    if request.filters:
        must_conditions = []
        if request.filters.get("entity_type"):
            must_conditions.append({"key": "entities", "match": {"any": [{"entity_type": request.filters["entity_type"]}]}})
        if request.filters.get("channel"):
            must_conditions.append({"key": "channel", "match": {"value": request.filters["channel"]}})
        if request.filters.get("since"):
            must_conditions.append({"key": "timestamp", "range": {"gte": request.filters["since"]}})
        if request.filters.get("until"):
            must_conditions.append({"key": "timestamp", "range": {"lte": request.filters["until"]}})
        if must_conditions: qdrant_filter = {"must": must_conditions}
    
    if request.types in ["both", "interactions"]:
        col = "memory_interactions_shared" if request.shared_only else "memory_interactions"
        interaction_res = await search_vectors(col, query_embedding, qdrant_filter or None, limit=request.limit)
        for r in interaction_res:
            payload = r.get("payload", {})
            results.append(SearchResult(
                id=payload.get("memory_id", ""), type="interaction", score=r.get("score", 0),
                snippet=payload.get("chunk_text", "")[:200] if payload.get("chunk_text") else "",
                timestamp=payload.get("timestamp", ""), metadata={"channel": payload.get("channel", "")}
            ))
            
    if request.types in ["both", "lessons"]:
        col = "memory_lessons_shared" if request.shared_only else "memory_lessons"
        lesson_res = await search_vectors(col, query_embedding, qdrant_filter or None, limit=request.limit)
        for r in lesson_res:
            payload = r.get("payload", {})
            results.append(SearchResult(
                id=payload.get("lesson_id", ""), type="lesson", score=r.get("score", 0),
                snippet=payload.get("summary", "")[:200] if payload.get("summary") else "",
                timestamp=payload.get("created_at", ""), metadata={"lesson_type": payload.get("lesson_type", "")}
            ))
            
    results.sort(key=lambda x: x.score, reverse=True)
    results = results[:request.limit]
    log_audit(agent["id"], "search", None, None, {"query": request.query, "results_count": len(results)})
    return SearchResponse(results=results, total=len(results), query=request.query)


# ============================================
# Agent API - Timeline
# ============================================

@router.get("/timeline/{entity_type}/{entity_id}")
async def get_timeline(
    entity_type: str, entity_id: str, since: str = None, until: str = None, 
    channel: str = None, limit: int = 50, offset: int = 0, agent: dict = Depends(verify_agent_key)
):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        query = "SELECT id, timestamp, channel, summary_text, has_documents, is_shared, 'interaction' as type FROM memories WHERE entities_json LIKE ?"
        params = [f'%"entity_id": "{entity_id}"%']
        if since:
            query += " AND timestamp >= ?"; params.append(since)
        if until:
            query += " AND timestamp <= ?"; params.append(until)
        if channel:
            query += " AND channel = ?"; params.append(channel)
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, params)
        entries = [TimelineEntry(
            id=row["id"], timestamp=row["timestamp"], type=row["type"], channel=row["channel"],
            summary_text=row["summary_text"] or "", has_documents=bool(row["has_documents"]), is_shared=bool(row["is_shared"])
        ) for row in cursor.fetchall()]
    log_audit(agent["id"], "timeline", entity_type, entity_id)
    return {"entries": entries, "entity_type": entity_type, "entity_id": entity_id}


# ============================================
# Agent API - Lessons
# ============================================

@router.get("/lessons", response_model=List[LessonResponse])
async def list_lessons(lesson_type: str = None, status: str = None, limit: int = 50, offset: int = 0, agent: dict = Depends(verify_agent_key)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        query, params = "SELECT * FROM memory_lessons WHERE 1=1", []
        if lesson_type:
            query += " AND lesson_type = ?"; params.append(lesson_type)
        if status:
            query += " AND status = ?"; params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, params)
        lessons = []
        for row in cursor.fetchall():
            lesson = dict(row)
            lesson["related_entities"] = json.loads(lesson.get("related_entities_json", "[]"))
            lesson["source_memory_ids"] = json.loads(lesson.get("source_memory_ids_json", "[]"))
            lesson["is_shared"] = bool(lesson["is_shared"])
            lessons.append(LessonResponse(**lesson))
    return lessons

@router.post("/lessons", response_model=LessonResponse)
async def create_lesson(data: LessonCreate, agent: dict = Depends(verify_agent_key)):
    now = datetime.now(timezone.utc).isoformat()
    lesson_id = str(uuid.uuid4())
    settings = get_memory_settings()
    status = "draft" if settings.get("lesson_approval_required", True) else "approved"
    summary = await summarize_text(data.body)
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_lessons (id, lesson_type, name, body, summary, status, is_shared, related_entities_json, source_memory_ids_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """, (lesson_id, data.lesson_type, data.name, data.body, summary, status,
              json.dumps([e.dict() for e in data.related_entities]), json.dumps(data.source_memory_ids), now, now))
    embedding = await generate_embedding(f"{data.name}\n\n{data.body}")
    if embedding:
        await upsert_vector("memory_lessons", lesson_id, embedding, {
            "lesson_id": lesson_id, "lesson_type": data.lesson_type, "name": data.name, "summary": summary, "created_at": now
        })
    log_audit(agent["id"], "create_lesson", "lesson", lesson_id)
    return LessonResponse(id=lesson_id, lesson_type=data.lesson_type, name=data.name, body=data.body, summary=summary, status=status,
                          is_shared=False, related_entities=data.related_entities, source_memory_ids=data.source_memory_ids, created_at=now, updated_at=now)

@router.patch("/lessons/{lesson_id}", response_model=LessonResponse)
async def update_lesson(lesson_id: str, data: LessonUpdate, agent: dict = Depends(verify_agent_key)):
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_lessons WHERE id = ?", (lesson_id,))
        if not cursor.fetchone(): raise HTTPException(status_code=404, detail="Lesson not found")
        updates, params = ["updated_at = ?"], [now]
        if data.name is not None:
            updates.append("name = ?"); params.append(data.name)
        if data.body is not None:
            updates.append("body = ?"); params.append(data.body)
            summary = await summarize_text(data.body)
            updates.append("summary = ?"); params.append(summary)
        if data.status is not None:
            updates.append("status = ?"); params.append(data.status)
        if data.related_entities is not None:
            updates.append("related_entities_json = ?"); params.append(json.dumps([e.dict() for e in data.related_entities]))
        params.append(lesson_id)
        cursor.execute(f"UPDATE memory_lessons SET {', '.join(updates)} WHERE id = ?", params)
        cursor.execute("SELECT * FROM memory_lessons WHERE id = ?", (lesson_id,))
        updated = dict(cursor.fetchone())
    log_audit(agent["id"], "update_lesson", "lesson", lesson_id)
    return LessonResponse(
        id=updated["id"], lesson_type=updated["lesson_type"], name=updated["name"], body=updated["body"], summary=updated["summary"], status=updated["status"],
        is_shared=bool(updated["is_shared"]), related_entities=json.loads(updated["related_entities_json"]), source_memory_ids=json.loads(updated["source_memory_ids_json"]),
        created_at=updated["created_at"], updated_at=updated["updated_at"]
    )


# ============================================
# Health & Init
# ============================================

@router.get("/health")
async def memory_health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@router.post("/init")
async def init_memory_system():
    await init_qdrant_collections()
    return {"message": "Memory system initialized"}
