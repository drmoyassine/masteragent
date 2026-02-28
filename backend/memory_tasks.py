# Memory System Background Tasks
# - OpenClaw Markdown Sync
# - Automated Lesson Mining
# - Rate Limiting
# - Agent Activity Monitoring

import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List
import uuid

from memory_db import get_memory_db_context
from memory_services import (
    get_memory_settings,
    get_system_prompt,
    generate_embedding,
    upsert_vector,
    call_llm
)

logger = logging.getLogger(__name__)

# ============================================
# OpenClaw Markdown Sync
# ============================================

async def sync_to_openclaw():
    """Export memories and lessons to OpenClaw Markdown format"""
    settings = get_memory_settings()
    
    if not settings.get("openclaw_sync_enabled"):
        return {"status": "disabled"}
    
    sync_path = settings.get("openclaw_sync_path", "")
    if not sync_path:
        return {"status": "error", "message": "Sync path not configured"}
    
    sync_type = settings.get("openclaw_sync_type", "filesystem")
    
    try:
        base_path = Path(sync_path)
        base_path.mkdir(parents=True, exist_ok=True)
        
        # Create directory structure
        memories_path = base_path / "memories"
        lessons_path = base_path / "lessons"
        entities_path = base_path / "entities"
        
        for p in [memories_path, lessons_path, entities_path]:
            p.mkdir(exist_ok=True)
        
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            
            # Export memories grouped by date
            cursor.execute("""
                SELECT DATE(timestamp) as date, COUNT(*) as count
                FROM memories
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
                LIMIT 30
            """)
            
            dates = cursor.fetchall()
            
            for date_row in dates:
                date_str = date_row["date"]
                date_path = memories_path / f"{date_str}.md"
                
                cursor.execute("""
                    SELECT id, timestamp, channel, summary_text, raw_text, entities_json
                    FROM memories
                    WHERE DATE(timestamp) = ?
                    ORDER BY timestamp
                """, (date_str,))
                
                memories = cursor.fetchall()
                
                # Generate Markdown
                md_content = f"# Memories - {date_str}\n\n"
                
                for mem in memories:
                    time_str = mem["timestamp"].split("T")[1][:5] if "T" in mem["timestamp"] else ""
                    md_content += f"## {time_str} - {mem['channel'].title()}\n\n"
                    
                    if mem["summary_text"]:
                        md_content += f"**Summary:** {mem['summary_text']}\n\n"
                    
                    entities = json.loads(mem.get("entities_json", "[]"))
                    if entities:
                        md_content += "**Entities:** "
                        md_content += ", ".join([f"{e.get('name')} ({e.get('type')})" for e in entities])
                        md_content += "\n\n"
                    
                    md_content += f"```\n{mem['raw_text'][:500]}{'...' if len(mem['raw_text']) > 500 else ''}\n```\n\n"
                    md_content += "---\n\n"
                
                date_path.write_text(md_content)
            
            # Export lessons
            cursor.execute("""
                SELECT id, lesson_type, name, body, status, created_at
                FROM memory_lessons
                WHERE status = 'approved'
                ORDER BY lesson_type, created_at DESC
            """)
            
            lessons = cursor.fetchall()
            
            # Group by type
            lessons_by_type = {}
            for lesson in lessons:
                lesson_type = lesson["lesson_type"]
                if lesson_type not in lessons_by_type:
                    lessons_by_type[lesson_type] = []
                lessons_by_type[lesson_type].append(lesson)
            
            # Write lesson files
            for lesson_type, type_lessons in lessons_by_type.items():
                type_path = lessons_path / f"{lesson_type.lower().replace(' ', '_')}.md"
                
                md_content = f"# {lesson_type} Lessons\n\n"
                
                for lesson in type_lessons:
                    md_content += f"## {lesson['name']}\n\n"
                    md_content += f"{lesson['body']}\n\n"
                    md_content += f"*Created: {lesson['created_at'][:10]}*\n\n"
                    md_content += "---\n\n"
                
                type_path.write_text(md_content)
            
            # Write index file
            index_path = base_path / "README.md"
            index_content = f"# Memory System Export\n\n"
            index_content += f"*Last updated: {datetime.now(timezone.utc).isoformat()}*\n\n"
            index_content += "## Structure\n\n"
            index_content += "- `memories/` - Daily memory logs\n"
            index_content += "- `lessons/` - Curated lessons by type\n"
            index_content += "- `entities/` - Entity profiles\n\n"
            index_content += f"## Stats\n\n"
            index_content += f"- **Days with memories:** {len(dates)}\n"
            index_content += f"- **Lesson types:** {len(lessons_by_type)}\n"
            index_content += f"- **Total lessons:** {len(lessons)}\n"
            
            index_path.write_text(index_content)
        
        return {
            "status": "success",
            "sync_path": str(base_path),
            "memories_synced": len(dates),
            "lessons_synced": len(lessons),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"OpenClaw sync error: {e}")
        return {"status": "error", "message": str(e)}

# ============================================
# Automated Lesson Mining
# ============================================

async def mine_lessons():
    """Automatically extract lessons from recent interactions"""
    settings = get_memory_settings()
    
    if not settings.get("auto_lesson_enabled"):
        return {"status": "disabled"}
    
    threshold = settings.get("auto_lesson_threshold", 5)
    
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            
            # Find entity clusters with enough interactions
            cursor.execute("""
                SELECT entities_json, COUNT(*) as interaction_count
                FROM memories
                WHERE created_at > datetime('now', '-7 days')
                GROUP BY entities_json
                HAVING interaction_count >= ?
                ORDER BY interaction_count DESC
                LIMIT 10
            """, (threshold,))
            
            clusters = cursor.fetchall()
            lessons_created = 0
            
            for cluster in clusters:
                entities = json.loads(cluster["entities_json"])
                if not entities:
                    continue
                
                primary_entity = next((e for e in entities if e.get("role") == "primary"), entities[0])
                
                # Get recent interactions for this entity pattern
                cursor.execute("""
                    SELECT raw_text, summary_text, channel, timestamp
                    FROM memories
                    WHERE entities_json = ?
                    ORDER BY timestamp DESC
                    LIMIT 10
                """, (cluster["entities_json"],))
                
                interactions = cursor.fetchall()
                
                # Check if we already have a lesson for this pattern recently
                cursor.execute("""
                    SELECT id FROM memory_lessons
                    WHERE related_entities_json LIKE ?
                    AND created_at > datetime('now', '-7 days')
                """, (f'%{primary_entity.get("name", "")}%',))
                
                if cursor.fetchone():
                    continue  # Skip if lesson already exists
                
                # Prepare context for lesson extraction
                interactions_text = "\n\n".join([
                    f"[{i['channel']} - {i['timestamp'][:10]}]\n{i['summary_text'] or i['raw_text'][:300]}"
                    for i in interactions
                ])
                
                # Get lesson extraction prompt
                prompt_template = get_system_prompt("lesson_extraction")
                if not prompt_template:
                    continue
                
                prompt = prompt_template.replace("{entity}", primary_entity.get("name", ""))
                prompt = prompt.replace("{interactions}", interactions_text)
                
                # Call LLM to extract lesson
                response = await call_llm(prompt, max_tokens=500, task_type="summarization")
                
                if not response:
                    continue
                
                try:
                    lesson_data = json.loads(response)
                except Exception as e:
                    logger.error(f"Failed to parse auto-mined lesson JSON: {e}")
                    continue
                
                # Create lesson
                lesson_id = str(uuid.uuid4())
                now = datetime.now(timezone.utc).isoformat()
                
                cursor.execute("""
                    INSERT INTO memory_lessons (id, lesson_type, name, body, summary, status, is_shared,
                                                related_entities_json, source_memory_ids_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'draft', 0, ?, ?, ?, ?)
                """, (
                    lesson_id,
                    lesson_data.get("type", "Other"),
                    lesson_data.get("name", "Untitled Lesson"),
                    lesson_data.get("body", ""),
                    lesson_data.get("body", "")[:200],
                    json.dumps(entities),
                    json.dumps([i["id"] for i in interactions if "id" in i]),
                    now, now
                ))
                
                # Generate and store embedding
                embedding = await generate_embedding(f"{lesson_data.get('name', '')}\n\n{lesson_data.get('body', '')}")
                if embedding:
                    await upsert_vector(
                        "memory_lessons",
                        lesson_id,
                        embedding,
                        {
                            "lesson_id": lesson_id,
                            "lesson_type": lesson_data.get("type", "Other"),
                            "name": lesson_data.get("name", ""),
                            "summary": lesson_data.get("body", "")[:200],
                            "created_at": now
                        }
                    )
                
                lessons_created += 1
                logger.info(f"Auto-mined lesson: {lesson_data.get('name', '')}")
            
            return {
                "status": "success",
                "lessons_created": lessons_created,
                "clusters_analyzed": len(clusters),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
    except Exception as e:
        logger.error(f"Lesson mining error: {e}")
        return {"status": "error", "message": str(e)}

# ============================================
# Rate Limiting
# ============================================

# In-memory rate limit tracking
_rate_limits: Dict[str, List[datetime]] = {}

def check_rate_limit(agent_id: str) -> bool:
    """Check if agent is within rate limit. Returns True if allowed."""
    settings = get_memory_settings()
    
    if not settings.get("rate_limit_enabled"):
        return True
    
    limit_per_minute = settings.get("rate_limit_per_minute", 60)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=1)
    
    # Clean old entries
    if agent_id in _rate_limits:
        _rate_limits[agent_id] = [t for t in _rate_limits[agent_id] if t > window_start]
    else:
        _rate_limits[agent_id] = []
    
    # Check limit
    if len(_rate_limits[agent_id]) >= limit_per_minute:
        return False
    
    # Add current request
    _rate_limits[agent_id].append(now)
    return True

def get_rate_limit_status(agent_id: str) -> Dict[str, Any]:
    """Get current rate limit status for an agent"""
    settings = get_memory_settings()
    
    if not settings.get("rate_limit_enabled"):
        return {"enabled": False}
    
    limit_per_minute = settings.get("rate_limit_per_minute", 60)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=1)
    
    requests_in_window = len([t for t in _rate_limits.get(agent_id, []) if t > window_start])
    
    return {
        "enabled": True,
        "limit_per_minute": limit_per_minute,
        "requests_used": requests_in_window,
        "requests_remaining": max(0, limit_per_minute - requests_in_window)
    }

# ============================================
# Agent Activity Monitoring
# ============================================

def get_agent_stats(agent_id: str = None, days: int = 7) -> Dict[str, Any]:
    """Get agent activity statistics"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        if agent_id:
            # Stats for specific agent
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_actions,
                    COUNT(DISTINCT DATE(timestamp)) as active_days,
                    action,
                    COUNT(*) as action_count
                FROM memory_audit_log
                WHERE agent_id = ?
                AND timestamp > datetime('now', ?)
                GROUP BY action
            """, (agent_id, f'-{days} days'))
        else:
            # Stats for all agents
            cursor.execute("""
                SELECT 
                    agent_id,
                    COUNT(*) as total_actions,
                    COUNT(DISTINCT DATE(timestamp)) as active_days
                FROM memory_audit_log
                WHERE timestamp > datetime('now', ?)
                GROUP BY agent_id
                ORDER BY total_actions DESC
            """, (f'-{days} days',))
        
        rows = cursor.fetchall()
        
        if agent_id:
            total = sum(r["action_count"] for r in rows)
            by_action = {r["action"]: r["action_count"] for r in rows}
            return {
                "agent_id": agent_id,
                "period_days": days,
                "total_actions": total,
                "by_action": by_action
            }
        else:
            return {
                "period_days": days,
                "agents": [
                    {
                        "agent_id": r["agent_id"],
                        "total_actions": r["total_actions"],
                        "active_days": r["active_days"]
                    }
                    for r in rows
                ]
            }

def get_system_stats() -> Dict[str, Any]:
    """Get overall system statistics"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Memory stats
        cursor.execute("SELECT COUNT(*) as count FROM memories")
        memory_count = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM memory_documents")
        doc_count = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM memory_lessons")
        lesson_count = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM memory_lessons WHERE status = 'draft'")
        draft_lesson_count = cursor.fetchone()["count"]
        
        # Agent stats
        cursor.execute("SELECT COUNT(*) as count FROM memory_agents WHERE is_active = 1")
        active_agent_count = cursor.fetchone()["count"]
        
        # Recent activity
        cursor.execute("""
            SELECT COUNT(*) as count FROM memories
            WHERE created_at > datetime('now', '-24 hours')
        """)
        memories_today = cursor.fetchone()["count"]
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM memory_audit_log
            WHERE timestamp > datetime('now', '-24 hours')
        """)
        actions_today = cursor.fetchone()["count"]
        
        return {
            "total_memories": memory_count,
            "total_documents": doc_count,
            "total_lessons": lesson_count,
            "draft_lessons": draft_lesson_count,
            "active_agents": active_agent_count,
            "memories_24h": memories_today,
            "actions_24h": actions_today,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# ============================================
# Background Task Runner
# ============================================

_running = False
_task = None

async def background_task_loop():
    """Main background task loop"""
    global _running
    _running = True
    
    while _running:
        try:
            settings = get_memory_settings()
            
            # OpenClaw sync
            if settings.get("openclaw_sync_enabled"):
                sync_freq = settings.get("openclaw_sync_frequency", 5)  # minutes
                await sync_to_openclaw()
                logger.info("OpenClaw sync completed")
            
            # Lesson mining
            if settings.get("auto_lesson_enabled"):
                await mine_lessons()
                logger.info("Lesson mining completed")
            
        except Exception as e:
            logger.error(f"Background task error: {e}")
        
        # Wait before next iteration
        await asyncio.sleep(300)  # 5 minutes

def start_background_tasks():
    """Start background task runner"""
    global _task
    if _task is None:
        _task = asyncio.create_task(background_task_loop())
        logger.info("Background tasks started")

def stop_background_tasks():
    """Stop background task runner"""
    global _running, _task
    _running = False
    if _task:
        _task.cancel()
        _task = None
        logger.info("Background tasks stopped")
