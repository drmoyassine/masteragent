"""
memory/admin.py — Admin UI endpoints for memory system

Auth: JWT (`require_admin_auth`) mapped from the Prompt Manager users DB.
Handles explorer, memory views, admin lessons tracking, stats, syncing, etc.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from memory_db import get_memory_db_context
from memory_models import LessonCreate, LessonUpdate, SearchRequest
from memory_services import delete_vector, generate_embedding, search_vectors, summarize_text
from memory_tasks import (
    get_agent_stats, get_system_stats, mine_lessons, sync_to_openclaw
)
from memory.auth import require_admin_auth

router = APIRouter()


# ============================================
# Admin UI - Memory Explorer Endpoints
# ============================================

@router.get("/daily/{date}")
async def get_daily_memories(date: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, channel, raw_text, summary_text, has_documents, 
                   is_shared, entities_json, metadata_json
            FROM memories
            WHERE DATE(timestamp) = ?
            ORDER BY timestamp DESC
        """, (date,))
        memories = []
        for row in cursor.fetchall():
            memory = dict(row)
            memory["has_documents"] = bool(memory["has_documents"])
            memory["is_shared"] = bool(memory["is_shared"])
            memory["entities"] = json.loads(memory.get("entities_json", "[]"))
            memory["metadata"] = json.loads(memory.get("metadata_json", "{}"))
            del memory["entities_json"]
            del memory["metadata_json"]
            memories.append(memory)
        return memories


@router.get("/memories/{memory_id}")
async def get_memory_detail(memory_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Memory not found")
        memory = dict(row)
        memory["has_documents"] = bool(memory["has_documents"])
        memory["is_shared"] = bool(memory["is_shared"])
        memory["entities"] = json.loads(memory.get("entities_json", "[]"))
        memory["metadata"] = json.loads(memory.get("metadata_json", "{}"))
        
        cursor.execute("SELECT * FROM memory_documents WHERE memory_id = ?", (memory_id,))
        memory["documents"] = [dict(doc) for doc in cursor.fetchall()]
        return memory


@router.post("/search")
async def search_memories_admin(request: SearchRequest, user: dict = Depends(require_admin_auth)):
    query_embedding = await generate_embedding(request.query)
    results = []
    
    if not query_embedding:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, timestamp, channel, raw_text, summary_text, entities_json
                FROM memories
                WHERE raw_text LIKE ? OR summary_text LIKE ?
            """
            params = [f"%{request.query}%", f"%{request.query}%"]
            if request.filters:
                if request.filters.get("channel"):
                    query += " AND channel = ?"
                    params.append(request.filters["channel"])
                if request.filters.get("date_from"):
                    query += " AND timestamp >= ?"
                    params.append(request.filters["date_from"])
                if request.filters.get("date_to"):
                    query += " AND timestamp <= ?"
                    params.append(request.filters["date_to"])
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(request.limit or 50)
            cursor.execute(query, params)
            
            for row in cursor.fetchall():
                results.append({
                    "id": row["id"], "memory_id": row["id"], "type": "interaction", "score": 1.0,
                    "text": row["summary_text"] or row["raw_text"][:200], "timestamp": row["timestamp"],
                    "channel": row["channel"], "entities": json.loads(row.get("entities_json", "[]"))
                })
    else:
        qdrant_filter = None
        if request.filters and request.filters.get("channel"):
            qdrant_filter = {"must": [{"key": "channel", "match": {"value": request.filters["channel"]}}]}
        
        vector_results = await search_vectors("memory_interactions", query_embedding, qdrant_filter, limit=request.limit or 50)
        memory_ids = [r.get("payload", {}).get("memory_id") for r in vector_results if r.get("payload", {}).get("memory_id")]
        
        if memory_ids:
            with get_memory_db_context() as conn:
                cursor = conn.cursor()
                placeholders = ",".join(["?" for _ in memory_ids])
                cursor.execute(f"SELECT id, timestamp, channel, raw_text, summary_text, entities_json FROM memories WHERE id IN ({placeholders})", memory_ids)
                memory_data = {row["id"]: dict(row) for row in cursor.fetchall()}
                
                for r in vector_results:
                    payload = r.get("payload", {})
                    memory_id = payload.get("memory_id")
                    if memory_id and memory_id in memory_data:
                        mem = memory_data[memory_id]
                        results.append({
                            "id": f"{memory_id}_{payload.get('chunk_index', 0)}", "memory_id": memory_id, "type": "interaction",
                            "score": r.get("score", 0), "text": mem["summary_text"] or mem["raw_text"][:200],
                            "timestamp": mem["timestamp"], "channel": mem["channel"],
                            "entities": json.loads(mem.get("entities_json", "[]"))
                        })
    return {"results": results, "total": len(results), "query": request.query}


@router.get("/admin/lessons")
async def list_lessons_admin(status: str = None, lesson_type: str = None, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        query, params = "SELECT * FROM memory_lessons WHERE 1=1", []
        if status and status != "all":
            query += " AND status = ?"; params.append(status)
        if lesson_type:
            query += " AND lesson_type = ?"; params.append(lesson_type)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        
        lessons = []
        for row in cursor.fetchall():
            lesson = dict(row)
            lesson["is_shared"] = bool(lesson.get("is_shared", 0))
            lesson["related_entities"] = json.loads(lesson.get("related_entities_json", "[]"))
            lesson["source_memory_ids"] = json.loads(lesson.get("source_memory_ids_json", "[]"))
            lessons.append(lesson)
        return lessons


@router.post("/admin/lessons")
async def create_lesson_admin(data: LessonCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    lesson_id = str(uuid.uuid4())
    summary = await summarize_text(data.body) if data.body else ""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_lessons (id, lesson_type, name, body, summary, status, is_shared, related_entities_json, source_memory_ids_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """, (lesson_id, data.lesson_type, data.name, data.body, summary, data.status or "draft",
              json.dumps([e.dict() for e in (data.related_entities or [])]), json.dumps(data.source_memory_ids or []), now, now))
    return {
        "id": lesson_id, "lesson_type": data.lesson_type, "name": data.name, "body": data.body, "summary": summary,
        "status": data.status or "draft", "is_shared": False, "created_at": now, "updated_at": now
    }


@router.put("/admin/lessons/{lesson_id}")
async def update_lesson_admin(lesson_id: str, data: LessonUpdate, user: dict = Depends(require_admin_auth)):
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
        if data.lesson_type is not None:
            updates.append("lesson_type = ?"); params.append(data.lesson_type)
        if data.status is not None:
            updates.append("status = ?"); params.append(data.status)
        
        params.append(lesson_id)
        cursor.execute(f"UPDATE memory_lessons SET {', '.join(updates)} WHERE id = ?", params)
        cursor.execute("SELECT * FROM memory_lessons WHERE id = ?", (lesson_id,))
        updated = dict(cursor.fetchone())
    return updated


@router.delete("/admin/lessons/{lesson_id}")
async def delete_lesson_admin(lesson_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_lessons WHERE id = ?", (lesson_id,))
    await delete_vector("memory_lessons", lesson_id)
    return {"message": "Deleted"}


@router.get("/admin/timeline/{entity_type}/{entity_id}")
async def get_timeline_admin(entity_type: str, entity_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, channel, raw_text, summary_text, has_documents
            FROM memories WHERE entities_json LIKE ? ORDER BY timestamp DESC LIMIT 100
        """, (f'%"{entity_id}"%',))
        
        return [{
            "id": row["id"], "timestamp": row["timestamp"], "channel": row["channel"],
            "summary_text": row["summary_text"], "raw_text": row["raw_text"], "has_documents": bool(row["has_documents"])
        } for row in cursor.fetchall()]


# ============================================
# Admin UI - Stats & Background Tasks
# ============================================

@router.get("/admin/stats")
async def get_stats(user: dict = Depends(require_admin_auth)):
    return get_system_stats()

@router.get("/admin/stats/agents")
async def get_all_agent_stats(days: int = 7, user: dict = Depends(require_admin_auth)):
    return get_agent_stats(days=days)

@router.get("/admin/stats/agents/{agent_id}")
async def get_single_agent_stats(agent_id: str, days: int = 7, user: dict = Depends(require_admin_auth)):
    return get_agent_stats(agent_id=agent_id, days=days)

@router.post("/admin/sync/openclaw")
async def trigger_openclaw_sync(user: dict = Depends(require_admin_auth)):
    return await sync_to_openclaw()

@router.post("/admin/tasks/mine-lessons")
async def trigger_lesson_mining(user: dict = Depends(require_admin_auth)):
    return await mine_lessons()
