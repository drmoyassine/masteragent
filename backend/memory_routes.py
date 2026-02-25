# Memory System API Routes
import os
import uuid
import json
import secrets
import logging
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form, Query
from jose import jwt, JWTError

from memory_db import get_memory_db_context
from memory_models import (
    EntityTypeCreate, EntityTypeResponse,
    EntitySubtypeCreate, EntitySubtypeResponse,
    LessonTypeCreate, LessonTypeResponse,
    ChannelTypeCreate, ChannelTypeResponse,
    AgentCreate, AgentResponse, AgentCreateResponse,
    SystemPromptCreate, SystemPromptResponse,
    MemorySettingsUpdate, MemorySettingsResponse,
    InteractionCreate, InteractionResponse, MemoryDetailResponse,
    LessonCreate, LessonResponse, LessonUpdate,
    SearchRequest, SearchResponse, SearchResult,
    TimelineEntry, RelatedEntity,
    LLMConfigCreate, LLMConfigResponse, LLMConfigUpdate
)
from memory_services import (
    generate_embedding, generate_embeddings_batch,
    upsert_vector, search_vectors, delete_vector,
    init_qdrant_collections,
    chunk_text, parse_document, summarize_text, extract_entities,
    scrub_pii, get_memory_settings, get_llm_config
)

logger = logging.getLogger(__name__)

# Create router
memory_router = APIRouter(prefix="/api/memory", tags=["Memory"])

# ============================================
# Admin Authentication (JWT)
# ============================================

ROOT_DIR = Path(__file__).parent
SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'promptsrc_secret_key_change_in_production_2024')
ALGORITHM = "HS256"
DB_PATH = ROOT_DIR / "prompt_manager.db"

def get_user_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def verify_jwt_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        return user_id
    except JWTError:
        return None

async def require_admin_auth(authorization: str = Header(None)):
    """Require JWT authentication for admin config endpoints"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
        
        user_id = verify_jwt_token(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        conn = get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            return dict(user)
        finally:
            conn.close()
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

# ============================================
# Agent Authentication (API Key)
# ============================================

async def verify_agent_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Verify agent API key and return agent info"""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM memory_agents 
            WHERE api_key_hash = ? AND is_active = 1
        """, (x_api_key,))
        agent = cursor.fetchone()
        
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Update last used
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE memory_agents SET last_used = ? WHERE id = ?",
            (now, agent["id"])
        )
        
        return dict(agent)

def log_audit(agent_id: str, action: str, resource_type: str = None, resource_id: str = None, details: dict = None):
    """Log agent activity"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_audit_log (id, agent_id, action, resource_type, resource_id, details_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            agent_id,
            action,
            resource_type,
            resource_id,
            json.dumps(details or {}),
            datetime.now(timezone.utc).isoformat()
        ))

# ============================================
# Admin Config Endpoints - Entity Types
# ============================================

@memory_router.get("/config/entity-types", response_model=List[EntityTypeResponse])
async def list_entity_types(user: dict = Depends(require_admin_auth)):
    """List all entity types"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_entity_types ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

@memory_router.post("/config/entity-types", response_model=EntityTypeResponse)
async def create_entity_type(data: EntityTypeCreate, user: dict = Depends(require_admin_auth)):
    """Create a new entity type"""
    now = datetime.now(timezone.utc).isoformat()
    type_id = str(uuid.uuid4())
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO memory_entity_types (id, name, description, icon, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (type_id, data.name, data.description, data.icon, now, now))
        except Exception as e:
            raise HTTPException(status_code=400, detail="Entity type already exists")
        
        cursor.execute("SELECT * FROM memory_entity_types WHERE id = ?", (type_id,))
        return dict(cursor.fetchone())

@memory_router.delete("/config/entity-types/{type_id}")
async def delete_entity_type(type_id: str, user: dict = Depends(require_admin_auth)):
    """Delete an entity type"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_entity_types WHERE id = ?", (type_id,))
    return {"message": "Deleted"}

# ============================================
# Admin Config Endpoints - Entity Subtypes
# ============================================

@memory_router.get("/config/entity-types/{type_id}/subtypes", response_model=List[EntitySubtypeResponse])
async def list_entity_subtypes(type_id: str, user: dict = Depends(require_admin_auth)):
    """List subtypes for an entity type"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM memory_entity_subtypes 
            WHERE entity_type_id = ? ORDER BY name
        """, (type_id,))
        return [dict(row) for row in cursor.fetchall()]

@memory_router.post("/config/entity-subtypes", response_model=EntitySubtypeResponse)
async def create_entity_subtype(data: EntitySubtypeCreate, user: dict = Depends(require_admin_auth)):
    """Create a new entity subtype"""
    now = datetime.now(timezone.utc).isoformat()
    subtype_id = str(uuid.uuid4())
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO memory_entity_subtypes (id, entity_type_id, name, description, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (subtype_id, data.entity_type_id, data.name, data.description, now))
        except Exception as e:
            raise HTTPException(status_code=400, detail="Subtype already exists for this entity type")
        
        cursor.execute("SELECT * FROM memory_entity_subtypes WHERE id = ?", (subtype_id,))
        return dict(cursor.fetchone())

@memory_router.delete("/config/entity-subtypes/{subtype_id}")
async def delete_entity_subtype(subtype_id: str, user: dict = Depends(require_admin_auth)):
    """Delete an entity subtype"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_entity_subtypes WHERE id = ?", (subtype_id,))
    return {"message": "Deleted"}

# ============================================
# Admin Config Endpoints - Lesson Types
# ============================================

@memory_router.get("/config/lesson-types", response_model=List[LessonTypeResponse])
async def list_lesson_types(user: dict = Depends(require_admin_auth)):
    """List all lesson types"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_lesson_types ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

@memory_router.post("/config/lesson-types", response_model=LessonTypeResponse)
async def create_lesson_type(data: LessonTypeCreate, user: dict = Depends(require_admin_auth)):
    """Create a new lesson type"""
    now = datetime.now(timezone.utc).isoformat()
    type_id = str(uuid.uuid4())
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO memory_lesson_types (id, name, description, color, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (type_id, data.name, data.description, data.color, now))
        except:
            raise HTTPException(status_code=400, detail="Lesson type already exists")
        
        cursor.execute("SELECT * FROM memory_lesson_types WHERE id = ?", (type_id,))
        return dict(cursor.fetchone())

@memory_router.delete("/config/lesson-types/{type_id}")
async def delete_lesson_type(type_id: str, user: dict = Depends(require_admin_auth)):
    """Delete a lesson type"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_lesson_types WHERE id = ?", (type_id,))
    return {"message": "Deleted"}

# ============================================
# Admin Config Endpoints - Channel Types
# ============================================

@memory_router.get("/config/channel-types", response_model=List[ChannelTypeResponse])
async def list_channel_types(user: dict = Depends(require_admin_auth)):
    """List all channel types"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_channel_types ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

@memory_router.post("/config/channel-types", response_model=ChannelTypeResponse)
async def create_channel_type(data: ChannelTypeCreate, user: dict = Depends(require_admin_auth)):
    """Create a new channel type"""
    now = datetime.now(timezone.utc).isoformat()
    type_id = str(uuid.uuid4())
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO memory_channel_types (id, name, description, icon, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (type_id, data.name, data.description, data.icon, now))
        except:
            raise HTTPException(status_code=400, detail="Channel type already exists")
        
        cursor.execute("SELECT * FROM memory_channel_types WHERE id = ?", (type_id,))
        return dict(cursor.fetchone())

@memory_router.delete("/config/channel-types/{type_id}")
async def delete_channel_type(type_id: str, user: dict = Depends(require_admin_auth)):
    """Delete a channel type"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_channel_types WHERE id = ?", (type_id,))
    return {"message": "Deleted"}

# ============================================
# Admin Config Endpoints - Agents
# ============================================

@memory_router.get("/config/agents", response_model=List[AgentResponse])
async def list_agents(user: dict = Depends(require_admin_auth)):
    """List all registered agents"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_agents ORDER BY created_at DESC")
        agents = []
        for row in cursor.fetchall():
            agent = dict(row)
            agent["is_active"] = bool(agent["is_active"])
            agents.append(agent)
        return agents

@memory_router.post("/config/agents", response_model=AgentCreateResponse)
async def create_agent(data: AgentCreate, user: dict = Depends(require_admin_auth)):
    """Create a new agent and return API key"""
    now = datetime.now(timezone.utc).isoformat()
    agent_id = str(uuid.uuid4())
    api_key = f"mem_{secrets.token_urlsafe(32)}"
    api_key_preview = f"{api_key[:7]}...{api_key[-4:]}"
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_agents (id, name, description, api_key_hash, api_key_preview, access_level, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (agent_id, data.name, data.description, api_key, api_key_preview, data.access_level, now))
        
        return AgentCreateResponse(
            id=agent_id,
            name=data.name,
            description=data.description,
            api_key=api_key,
            api_key_preview=api_key_preview,
            access_level=data.access_level,
            is_active=True,
            created_at=now,
            last_used=None
        )

@memory_router.patch("/config/agents/{agent_id}")
async def update_agent(agent_id: str, user: dict = Depends(require_admin_auth), is_active: bool = None, access_level: str = None):
    """Update agent settings"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        updates = []
        params = []
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        if access_level is not None:
            updates.append("access_level = ?")
            params.append(access_level)
        
        if updates:
            params.append(agent_id)
            cursor.execute(f"UPDATE memory_agents SET {', '.join(updates)} WHERE id = ?", params)
    
    return {"message": "Updated"}

@memory_router.delete("/config/agents/{agent_id}")
async def delete_agent(agent_id: str, user: dict = Depends(require_admin_auth)):
    """Delete an agent"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_agents WHERE id = ?", (agent_id,))
    return {"message": "Deleted"}

# ============================================
# Admin Config Endpoints - System Prompts
# ============================================

@memory_router.get("/config/system-prompts", response_model=List[SystemPromptResponse])
async def list_system_prompts(user: dict = Depends(require_admin_auth)):
    """List all system prompts"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_system_prompts ORDER BY prompt_type, created_at DESC")
        prompts = []
        for row in cursor.fetchall():
            prompt = dict(row)
            prompt["is_active"] = bool(prompt["is_active"])
            prompts.append(prompt)
        return prompts

@memory_router.post("/config/system-prompts", response_model=SystemPromptResponse)
async def create_system_prompt(data: SystemPromptCreate, user: dict = Depends(require_admin_auth)):
    """Create a new system prompt"""
    now = datetime.now(timezone.utc).isoformat()
    prompt_id = str(uuid.uuid4())
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Deactivate other prompts of same type if this one is active
        if data.is_active:
            cursor.execute("""
                UPDATE memory_system_prompts SET is_active = 0 
                WHERE prompt_type = ?
            """, (data.prompt_type,))
        
        cursor.execute("""
            INSERT INTO memory_system_prompts (id, prompt_type, name, prompt_text, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (prompt_id, data.prompt_type, data.name, data.prompt_text, 1 if data.is_active else 0, now, now))
        
        cursor.execute("SELECT * FROM memory_system_prompts WHERE id = ?", (prompt_id,))
        row = cursor.fetchone()
        result = dict(row)
        result["is_active"] = bool(result["is_active"])
        return result

@memory_router.put("/config/system-prompts/{prompt_id}", response_model=SystemPromptResponse)
async def update_system_prompt(prompt_id: str, data: SystemPromptCreate, user: dict = Depends(require_admin_auth)):
    """Update a system prompt"""
    now = datetime.now(timezone.utc).isoformat()
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Get current prompt type
        cursor.execute("SELECT prompt_type FROM memory_system_prompts WHERE id = ?", (prompt_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        # Deactivate other prompts of same type if this one is active
        if data.is_active:
            cursor.execute("""
                UPDATE memory_system_prompts SET is_active = 0 
                WHERE prompt_type = ? AND id != ?
            """, (data.prompt_type, prompt_id))
        
        cursor.execute("""
            UPDATE memory_system_prompts 
            SET prompt_type = ?, name = ?, prompt_text = ?, is_active = ?, updated_at = ?
            WHERE id = ?
        """, (data.prompt_type, data.name, data.prompt_text, 1 if data.is_active else 0, now, prompt_id))
        
        cursor.execute("SELECT * FROM memory_system_prompts WHERE id = ?", (prompt_id,))
        row = cursor.fetchone()
        result = dict(row)
        result["is_active"] = bool(result["is_active"])
        return result

@memory_router.delete("/config/system-prompts/{prompt_id}")
async def delete_system_prompt(prompt_id: str, user: dict = Depends(require_admin_auth)):
    """Delete a system prompt"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_system_prompts WHERE id = ?", (prompt_id,))
    return {"message": "Deleted"}

# ============================================
# Admin Config Endpoints - LLM Configurations
# ============================================

@memory_router.get("/config/llm-configs", response_model=List[LLMConfigResponse])
async def list_llm_configs(user: dict = Depends(require_admin_auth)):
    """List all LLM configurations"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_configs ORDER BY task_type, created_at DESC")
        configs = []
        for row in cursor.fetchall():
            config = dict(row)
            configs.append(LLMConfigResponse(
                id=config["id"],
                task_type=config["task_type"],
                provider=config["provider"],
                name=config["name"],
                api_base_url=config.get("api_base_url", ""),
                api_key_preview=config.get("api_key_preview", ""),
                model_name=config.get("model_name", ""),
                is_active=bool(config.get("is_active", 0)),
                extra_config=json.loads(config.get("extra_config_json", "{}")),
                created_at=config["created_at"],
                updated_at=config["updated_at"]
            ))
        return configs

@memory_router.get("/config/llm-configs/{task_type}", response_model=LLMConfigResponse)
async def get_llm_config_by_task(task_type: str, user: dict = Depends(require_admin_auth)):
    """Get active LLM config for a task type"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM memory_llm_configs 
            WHERE task_type = ? AND is_active = 1
            ORDER BY updated_at DESC LIMIT 1
        """, (task_type,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No active LLM config for {task_type}")
        
        config = dict(row)
        return LLMConfigResponse(
            id=config["id"],
            task_type=config["task_type"],
            provider=config["provider"],
            name=config["name"],
            api_base_url=config.get("api_base_url", ""),
            api_key_preview=config.get("api_key_preview", ""),
            model_name=config.get("model_name", ""),
            is_active=bool(config.get("is_active", 0)),
            extra_config=json.loads(config.get("extra_config_json", "{}")),
            created_at=config["created_at"],
            updated_at=config["updated_at"]
        )

@memory_router.post("/config/llm-configs", response_model=LLMConfigResponse)
async def create_llm_config(data: LLMConfigCreate, user: dict = Depends(require_admin_auth)):
    """Create a new LLM configuration"""
    now = datetime.now(timezone.utc).isoformat()
    config_id = str(uuid.uuid4())
    
    # Create preview of API key
    api_key_preview = ""
    if data.api_key:
        api_key_preview = f"{data.api_key[:4]}...{data.api_key[-4:]}" if len(data.api_key) > 8 else "****"
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Deactivate other configs for the same task type if this one is active
        if data.is_active:
            cursor.execute("""
                UPDATE memory_llm_configs SET is_active = 0 
                WHERE task_type = ?
            """, (data.task_type,))
        
        cursor.execute("""
            INSERT INTO memory_llm_configs (id, task_type, provider, name, api_base_url, api_key_encrypted, api_key_preview, model_name, is_active, extra_config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            config_id, data.task_type, data.provider, data.name,
            data.api_base_url or "", data.api_key or "", api_key_preview,
            data.model_name or "", 1 if data.is_active else 0,
            json.dumps(data.extra_config or {}), now, now
        ))
        
        return LLMConfigResponse(
            id=config_id,
            task_type=data.task_type,
            provider=data.provider,
            name=data.name,
            api_base_url=data.api_base_url or "",
            api_key_preview=api_key_preview,
            model_name=data.model_name or "",
            is_active=data.is_active,
            extra_config=data.extra_config or {},
            created_at=now,
            updated_at=now
        )

@memory_router.put("/config/llm-configs/{config_id}", response_model=LLMConfigResponse)
async def update_llm_config(config_id: str, data: LLMConfigUpdate, user: dict = Depends(require_admin_auth)):
    """Update an LLM configuration"""
    now = datetime.now(timezone.utc).isoformat()
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM memory_llm_configs WHERE id = ?", (config_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="LLM config not found")
        
        existing = dict(existing)
        
        updates = ["updated_at = ?"]
        params = [now]
        
        if data.name is not None:
            updates.append("name = ?")
            params.append(data.name)
        if data.api_base_url is not None:
            updates.append("api_base_url = ?")
            params.append(data.api_base_url)
        if data.api_key is not None:
            updates.append("api_key_encrypted = ?")
            params.append(data.api_key)
            api_key_preview = f"{data.api_key[:4]}...{data.api_key[-4:]}" if len(data.api_key) > 8 else "****"
            updates.append("api_key_preview = ?")
            params.append(api_key_preview)
        if data.model_name is not None:
            updates.append("model_name = ?")
            params.append(data.model_name)
        if data.is_active is not None:
            # Deactivate other configs for the same task type
            if data.is_active:
                cursor.execute("""
                    UPDATE memory_llm_configs SET is_active = 0 
                    WHERE task_type = ? AND id != ?
                """, (existing["task_type"], config_id))
            updates.append("is_active = ?")
            params.append(1 if data.is_active else 0)
        if data.extra_config is not None:
            updates.append("extra_config_json = ?")
            params.append(json.dumps(data.extra_config))
        
        params.append(config_id)
        cursor.execute(f"UPDATE memory_llm_configs SET {', '.join(updates)} WHERE id = ?", params)
        
        cursor.execute("SELECT * FROM memory_llm_configs WHERE id = ?", (config_id,))
        updated = dict(cursor.fetchone())
        
        return LLMConfigResponse(
            id=updated["id"],
            task_type=updated["task_type"],
            provider=updated["provider"],
            name=updated["name"],
            api_base_url=updated.get("api_base_url", ""),
            api_key_preview=updated.get("api_key_preview", ""),
            model_name=updated.get("model_name", ""),
            is_active=bool(updated.get("is_active", 0)),
            extra_config=json.loads(updated.get("extra_config_json", "{}")),
            created_at=updated["created_at"],
            updated_at=updated["updated_at"]
        )

@memory_router.delete("/config/llm-configs/{config_id}")
async def delete_llm_config(config_id: str, user: dict = Depends(require_admin_auth)):
    """Delete an LLM configuration"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_llm_configs WHERE id = ?", (config_id,))
    return {"message": "Deleted"}

# ============================================
# Admin Config Endpoints - Settings
# ============================================

@memory_router.get("/config/settings", response_model=MemorySettingsResponse)
async def get_settings_endpoint(user: dict = Depends(require_admin_auth)):
    """Get memory system settings"""
    settings = get_memory_settings()
    return MemorySettingsResponse(
        chunk_size=settings.get("chunk_size", 400),
        chunk_overlap=settings.get("chunk_overlap", 80),
        auto_lesson_enabled=bool(settings.get("auto_lesson_enabled", 1)),
        auto_lesson_threshold=settings.get("auto_lesson_threshold", 5),
        lesson_approval_required=bool(settings.get("lesson_approval_required", 1)),
        pii_scrubbing_enabled=bool(settings.get("pii_scrubbing_enabled", 1)),
        auto_share_scrubbed=bool(settings.get("auto_share_scrubbed", 0)),
        openclaw_sync_enabled=bool(settings.get("openclaw_sync_enabled", 0)),
        openclaw_sync_path=settings.get("openclaw_sync_path", ""),
        openclaw_sync_type=settings.get("openclaw_sync_type", "filesystem"),
        openclaw_sync_frequency=settings.get("openclaw_sync_frequency", 5),
        rate_limit_enabled=bool(settings.get("rate_limit_enabled", 0)),
        rate_limit_per_minute=settings.get("rate_limit_per_minute", 60),
        default_agent_access=settings.get("default_agent_access", "private")
    )

@memory_router.put("/config/settings", response_model=MemorySettingsResponse)
async def update_settings_endpoint(data: MemorySettingsUpdate, user: dict = Depends(require_admin_auth)):
    """Update memory system settings"""
    now = datetime.now(timezone.utc).isoformat()
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        for field, value in data.dict(exclude_unset=True).items():
            if value is not None:
                if isinstance(value, bool):
                    value = 1 if value else 0
                updates.append(f"{field} = ?")
                params.append(value)
        
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            cursor.execute(f"UPDATE memory_settings SET {', '.join(updates)} WHERE id = 1", params)
    
    return await get_settings_endpoint(user)

# ============================================
# Agent API - Interactions (Ingest)
# ============================================

@memory_router.post("/interactions", response_model=InteractionResponse)
async def ingest_interaction(
    text: str = Form(...),
    channel: str = Form(...),
    entities: str = Form("[]"),  # JSON string
    metadata: str = Form("{}"),  # JSON string
    files: List[UploadFile] = File(default=[]),
    agent: dict = Depends(verify_agent_key)
):
    """
    Ingest a new interaction with optional file attachments.
    This is the main entry point for agents to push data.
    """
    now = datetime.now(timezone.utc).isoformat()
    memory_id = str(uuid.uuid4())
    
    try:
        entities_list = json.loads(entities)
    except:
        entities_list = []
    
    try:
        metadata_dict = json.loads(metadata)
    except:
        metadata_dict = {}
    
    settings = get_memory_settings()
    
    # Parse uploaded documents
    parsed_docs = []
    all_text = text
    
    for file in files:
        content = await file.read()
        parsed = await parse_document(content, file.filename, file.content_type)
        
        doc_id = str(uuid.uuid4())
        parsed_docs.append({
            "id": doc_id,
            "filename": file.filename,
            "file_type": file.content_type,
            "file_size": len(content),
            "parsed_text": parsed["text"]
        })
        
        if parsed["text"]:
            all_text += f"\n\n---\n[Document: {file.filename}]\n{parsed['text']}"
    
    # Generate summary
    summary = await summarize_text(all_text)
    
    # Extract entities if not provided
    if not entities_list:
        extracted = await extract_entities(all_text)
        entities_list = extracted
    
    # Chunk and embed
    chunks = chunk_text(
        all_text,
        chunk_size=settings.get("chunk_size", 400),
        chunk_overlap=settings.get("chunk_overlap", 80)
    )
    
    # Generate embeddings for chunks
    embeddings = await generate_embeddings_batch(chunks) if chunks else []
    
    # PII Scrubbing for shared memory (if enabled)
    pii_scrubbed_text = None
    pii_scrubbed_summary = None
    scrubbed_chunks = []
    scrubbed_embeddings = []
    
    if settings.get("pii_scrubbing_enabled", False):
        pii_scrubbed_text = await scrub_pii(all_text)
        pii_scrubbed_summary = await scrub_pii(summary) if summary else ""
        scrubbed_chunks = chunk_text(
            pii_scrubbed_text,
            chunk_size=settings.get("chunk_size", 400),
            chunk_overlap=settings.get("chunk_overlap", 80)
        )
        scrubbed_embeddings = await generate_embeddings_batch(scrubbed_chunks) if scrubbed_chunks else []
    
    # Store memory in database
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Store private memory
        cursor.execute("""
            INSERT INTO memories (id, timestamp, channel, raw_text, summary_text, has_documents, 
                                  is_shared, entities_json, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """, (
            memory_id, now, channel, text, summary,
            1 if parsed_docs else 0,
            json.dumps(entities_list), json.dumps(metadata_dict),
            now, now
        ))
        
        # Store documents
        for doc in parsed_docs:
            cursor.execute("""
                INSERT INTO memory_documents (id, memory_id, filename, file_type, file_size, parsed_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (doc["id"], memory_id, doc["filename"], doc["file_type"], doc["file_size"], doc["parsed_text"], now))
        
        # Store PII-scrubbed shared memory (if enabled and auto-share is on)
        if settings.get("pii_scrubbing_enabled") and settings.get("auto_share_scrubbed"):
            shared_memory_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO memories_shared (id, original_memory_id, timestamp, channel, scrubbed_text, 
                                            summary_text, has_documents, entities_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                shared_memory_id, memory_id, now, channel, pii_scrubbed_text, pii_scrubbed_summary,
                1 if parsed_docs else 0,
                json.dumps(entities_list), json.dumps(metadata_dict), now
            ))
            
            # Store scrubbed vectors in Qdrant shared collection
            for i, (chunk, embedding) in enumerate(zip(scrubbed_chunks, scrubbed_embeddings)):
                if embedding:
                    vector_id = f"{shared_memory_id}_{i}"
                    await upsert_vector(
                        "memory_shared",
                        vector_id,
                        embedding,
                        {
                            "memory_id": shared_memory_id,
                            "original_memory_id": memory_id,
                            "chunk_index": i,
                            "channel": channel,
                            "timestamp": now,
                            "entities": entities_list,
                            "is_shared": True
                        }
                    )
    
    # Store private vectors in Qdrant
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        if embedding:
            vector_id = f"{memory_id}_{i}"
            await upsert_vector(
                "memory_interactions",
                vector_id,
                embedding,
                {
                    "memory_id": memory_id,
                    "chunk_index": i,
                    "channel": channel,
                    "timestamp": now,
                    "entities": entities_list,
                    "is_shared": False
                }
            )
    
    # Log audit
    log_audit(agent["id"], "ingest_interaction", "memory", memory_id, {"channel": channel})
    
    return InteractionResponse(
        id=memory_id,
        timestamp=now,
        channel=channel,
        summary_text=summary,
        has_documents=bool(parsed_docs),
        entities=[RelatedEntity(**e) for e in entities_list],
        metadata=metadata_dict
    )

# ============================================
# Agent API - Search
# ============================================

@memory_router.post("/search", response_model=SearchResponse)
async def search_memories(
    request: SearchRequest,
    agent: dict = Depends(verify_agent_key)
):
    """Search memories and lessons using semantic search"""
    
    # Generate query embedding
    query_embedding = await generate_embedding(request.query)
    if not query_embedding:
        return SearchResponse(results=[], total=0, query=request.query)
    
    results = []
    
    # Build Qdrant filters
    qdrant_filter = {}
    if request.filters:
        must_conditions = []
        
        if "entity_type" in request.filters:
            must_conditions.append({
                "key": "entities",
                "match": {"any": [{"entity_type": request.filters["entity_type"]}]}
            })
        
        if "channel" in request.filters:
            must_conditions.append({
                "key": "channel",
                "match": {"value": request.filters["channel"]}
            })
        
        if "since" in request.filters:
            must_conditions.append({
                "key": "timestamp",
                "range": {"gte": request.filters["since"]}
            })
        
        if "until" in request.filters:
            must_conditions.append({
                "key": "timestamp",
                "range": {"lte": request.filters["until"]}
            })
        
        if must_conditions:
            qdrant_filter = {"must": must_conditions}
    
    # Search interactions
    if request.types in ["both", "interactions"]:
        collection = "memory_interactions_shared" if request.shared_only else "memory_interactions"
        interaction_results = await search_vectors(
            collection,
            query_embedding,
            qdrant_filter if qdrant_filter else None,
            limit=request.limit
        )
        
        for r in interaction_results:
            payload = r.get("payload", {})
            results.append(SearchResult(
                id=payload.get("memory_id", ""),
                type="interaction",
                score=r.get("score", 0),
                snippet=payload.get("chunk_text", "")[:200] if payload.get("chunk_text") else "",
                timestamp=payload.get("timestamp", ""),
                metadata={"channel": payload.get("channel", "")}
            ))
    
    # Search lessons
    if request.types in ["both", "lessons"]:
        collection = "memory_lessons_shared" if request.shared_only else "memory_lessons"
        lesson_results = await search_vectors(
            collection,
            query_embedding,
            qdrant_filter if qdrant_filter else None,
            limit=request.limit
        )
        
        for r in lesson_results:
            payload = r.get("payload", {})
            results.append(SearchResult(
                id=payload.get("lesson_id", ""),
                type="lesson",
                score=r.get("score", 0),
                snippet=payload.get("summary", "")[:200] if payload.get("summary") else "",
                timestamp=payload.get("created_at", ""),
                metadata={"lesson_type": payload.get("lesson_type", "")}
            ))
    
    # Sort by score and limit
    results.sort(key=lambda x: x.score, reverse=True)
    results = results[:request.limit]
    
    # Log audit
    log_audit(agent["id"], "search", None, None, {"query": request.query, "results_count": len(results)})
    
    return SearchResponse(
        results=results,
        total=len(results),
        query=request.query
    )

# ============================================
# Agent API - Timeline
# ============================================

@memory_router.get("/timeline/{entity_type}/{entity_id}")
async def get_timeline(
    entity_type: str,
    entity_id: str,
    since: str = None,
    until: str = None,
    channel: str = None,
    limit: int = 50,
    offset: int = 0,
    agent: dict = Depends(verify_agent_key)
):
    """Get chronological timeline for an entity"""
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Build query - search in entities_json
        query = """
            SELECT id, timestamp, channel, summary_text, has_documents, is_shared, 'interaction' as type
            FROM memories
            WHERE entities_json LIKE ?
        """
        params = [f'%"entity_id": "{entity_id}"%']
        
        if since:
            query += " AND timestamp >= ?"
            params.append(since)
        if until:
            query += " AND timestamp <= ?"
            params.append(until)
        if channel:
            query += " AND channel = ?"
            params.append(channel)
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        
        entries = []
        for row in cursor.fetchall():
            entries.append(TimelineEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                type=row["type"],
                channel=row["channel"],
                summary_text=row["summary_text"] or "",
                has_documents=bool(row["has_documents"]),
                is_shared=bool(row["is_shared"])
            ))
    
    # Log audit
    log_audit(agent["id"], "timeline", entity_type, entity_id)
    
    return {"entries": entries, "entity_type": entity_type, "entity_id": entity_id}

# ============================================
# Agent API - Lessons
# ============================================

@memory_router.get("/lessons", response_model=List[LessonResponse])
async def list_lessons(
    lesson_type: str = None,
    status: str = None,
    limit: int = 50,
    offset: int = 0,
    agent: dict = Depends(verify_agent_key)
):
    """List lessons with optional filters"""
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM memory_lessons WHERE 1=1"
        params = []
        
        if lesson_type:
            query += " AND lesson_type = ?"
            params.append(lesson_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        
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

@memory_router.post("/lessons", response_model=LessonResponse)
async def create_lesson(
    data: LessonCreate,
    agent: dict = Depends(verify_agent_key)
):
    """Create a new lesson"""
    now = datetime.now(timezone.utc).isoformat()
    lesson_id = str(uuid.uuid4())
    
    settings = get_memory_settings()
    status = "draft" if settings.get("lesson_approval_required", True) else "approved"
    
    # Generate summary
    summary = await summarize_text(data.body)
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO memory_lessons (id, lesson_type, name, body, summary, status, is_shared,
                                        related_entities_json, source_memory_ids_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """, (
            lesson_id, data.lesson_type, data.name, data.body, summary, status,
            json.dumps([e.dict() for e in data.related_entities]),
            json.dumps(data.source_memory_ids),
            now, now
        ))
    
    # Generate and store embedding
    embedding = await generate_embedding(f"{data.name}\n\n{data.body}")
    if embedding:
        await upsert_vector(
            "memory_lessons",
            lesson_id,
            embedding,
            {
                "lesson_id": lesson_id,
                "lesson_type": data.lesson_type,
                "name": data.name,
                "summary": summary,
                "created_at": now
            }
        )
    
    # Log audit
    log_audit(agent["id"], "create_lesson", "lesson", lesson_id)
    
    return LessonResponse(
        id=lesson_id,
        lesson_type=data.lesson_type,
        name=data.name,
        body=data.body,
        summary=summary,
        status=status,
        is_shared=False,
        related_entities=data.related_entities,
        source_memory_ids=data.source_memory_ids,
        created_at=now,
        updated_at=now
    )

@memory_router.patch("/lessons/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: str,
    data: LessonUpdate,
    agent: dict = Depends(verify_agent_key)
):
    """Update a lesson"""
    now = datetime.now(timezone.utc).isoformat()
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM memory_lessons WHERE id = ?", (lesson_id,))
        lesson = cursor.fetchone()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        
        updates = ["updated_at = ?"]
        params = [now]
        
        if data.name is not None:
            updates.append("name = ?")
            params.append(data.name)
        if data.body is not None:
            updates.append("body = ?")
            params.append(data.body)
            # Regenerate summary
            summary = await summarize_text(data.body)
            updates.append("summary = ?")
            params.append(summary)
        if data.status is not None:
            updates.append("status = ?")
            params.append(data.status)
        if data.related_entities is not None:
            updates.append("related_entities_json = ?")
            params.append(json.dumps([e.dict() for e in data.related_entities]))
        
        params.append(lesson_id)
        cursor.execute(f"UPDATE memory_lessons SET {', '.join(updates)} WHERE id = ?", params)
        
        cursor.execute("SELECT * FROM memory_lessons WHERE id = ?", (lesson_id,))
        updated = dict(cursor.fetchone())
    
    # Log audit
    log_audit(agent["id"], "update_lesson", "lesson", lesson_id)
    
    return LessonResponse(
        id=updated["id"],
        lesson_type=updated["lesson_type"],
        name=updated["name"],
        body=updated["body"],
        summary=updated["summary"],
        status=updated["status"],
        is_shared=bool(updated["is_shared"]),
        related_entities=json.loads(updated["related_entities_json"]),
        source_memory_ids=json.loads(updated["source_memory_ids_json"]),
        created_at=updated["created_at"],
        updated_at=updated["updated_at"]
    )

# ============================================
# Health & Init
# ============================================

@memory_router.get("/health")
async def memory_health():
    """Memory system health check"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@memory_router.post("/init")
async def init_memory_system():
    """Initialize Qdrant collections"""
    await init_qdrant_collections()
    return {"message": "Memory system initialized"}

# ============================================
# Admin UI - Memory Explorer Endpoints
# ============================================

@memory_router.get("/daily/{date}")
async def get_daily_memories(date: str, user: dict = Depends(require_admin_auth)):
    """Get all memories for a specific date (admin UI)"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Query memories for the date (timestamp starts with date)
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

@memory_router.get("/memories/{memory_id}")
async def get_memory_detail(memory_id: str, user: dict = Depends(require_admin_auth)):
    """Get full memory details including documents (admin UI)"""
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
        
        # Get documents
        cursor.execute("SELECT * FROM memory_documents WHERE memory_id = ?", (memory_id,))
        memory["documents"] = [dict(doc) for doc in cursor.fetchall()]
        
        return memory

@memory_router.post("/search")
async def search_memories_admin(request: SearchRequest, user: dict = Depends(require_admin_auth)):
    """Search memories from admin UI (JWT auth)"""
    # Generate query embedding
    query_embedding = await generate_embedding(request.query)
    
    results = []
    
    # If no embedding service configured, fall back to text search
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
                    "id": row["id"],
                    "memory_id": row["id"],
                    "type": "interaction",
                    "score": 1.0,
                    "text": row["summary_text"] or row["raw_text"][:200],
                    "timestamp": row["timestamp"],
                    "channel": row["channel"],
                    "entities": json.loads(row.get("entities_json", "[]"))
                })
    else:
        # Vector search
        qdrant_filter = None
        if request.filters:
            must_conditions = []
            if request.filters.get("channel"):
                must_conditions.append({"key": "channel", "match": {"value": request.filters["channel"]}})
            if must_conditions:
                qdrant_filter = {"must": must_conditions}
        
        vector_results = await search_vectors(
            "memory_interactions",
            query_embedding,
            qdrant_filter,
            limit=request.limit or 50
        )
        
        # Get full memory data for results
        memory_ids = [r.get("payload", {}).get("memory_id") for r in vector_results if r.get("payload", {}).get("memory_id")]
        
        if memory_ids:
            with get_memory_db_context() as conn:
                cursor = conn.cursor()
                placeholders = ",".join(["?" for _ in memory_ids])
                cursor.execute(f"""
                    SELECT id, timestamp, channel, raw_text, summary_text, entities_json
                    FROM memories WHERE id IN ({placeholders})
                """, memory_ids)
                
                memory_data = {row["id"]: dict(row) for row in cursor.fetchall()}
                
                for r in vector_results:
                    payload = r.get("payload", {})
                    memory_id = payload.get("memory_id")
                    if memory_id and memory_id in memory_data:
                        mem = memory_data[memory_id]
                        results.append({
                            "id": f"{memory_id}_{payload.get('chunk_index', 0)}",
                            "memory_id": memory_id,
                            "type": "interaction",
                            "score": r.get("score", 0),
                            "text": mem["summary_text"] or mem["raw_text"][:200],
                            "timestamp": mem["timestamp"],
                            "channel": mem["channel"],
                            "entities": json.loads(mem.get("entities_json", "[]"))
                        })
    
    return {"results": results, "total": len(results), "query": request.query}

@memory_router.get("/admin/lessons")
async def list_lessons_admin(
    status: str = None,
    lesson_type: str = None,
    user: dict = Depends(require_admin_auth)
):
    """List lessons for admin UI (JWT auth)"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM memory_lessons WHERE 1=1"
        params = []
        
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
        if lesson_type:
            query += " AND lesson_type = ?"
            params.append(lesson_type)
        
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

@memory_router.post("/admin/lessons")
async def create_lesson_admin(data: LessonCreate, user: dict = Depends(require_admin_auth)):
    """Create a lesson from admin UI"""
    now = datetime.now(timezone.utc).isoformat()
    lesson_id = str(uuid.uuid4())
    
    # Generate summary if body provided
    summary = await summarize_text(data.body) if data.body else ""
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO memory_lessons (id, lesson_type, name, body, summary, status, is_shared,
                                        related_entities_json, source_memory_ids_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """, (
            lesson_id, data.lesson_type, data.name, data.body, summary, data.status or "draft",
            json.dumps([e.dict() for e in (data.related_entities or [])]),
            json.dumps(data.source_memory_ids or []),
            now, now
        ))
    
    return {
        "id": lesson_id,
        "lesson_type": data.lesson_type,
        "name": data.name,
        "body": data.body,
        "summary": summary,
        "status": data.status or "draft",
        "is_shared": False,
        "created_at": now,
        "updated_at": now
    }

@memory_router.put("/admin/lessons/{lesson_id}")
async def update_lesson_admin(lesson_id: str, data: LessonUpdate, user: dict = Depends(require_admin_auth)):
    """Update a lesson from admin UI"""
    now = datetime.now(timezone.utc).isoformat()
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM memory_lessons WHERE id = ?", (lesson_id,))
        lesson = cursor.fetchone()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        
        updates = ["updated_at = ?"]
        params = [now]
        
        if data.name is not None:
            updates.append("name = ?")
            params.append(data.name)
        if data.body is not None:
            updates.append("body = ?")
            params.append(data.body)
        if data.lesson_type is not None:
            updates.append("lesson_type = ?")
            params.append(data.lesson_type)
        if data.status is not None:
            updates.append("status = ?")
            params.append(data.status)
        
        params.append(lesson_id)
        cursor.execute(f"UPDATE memory_lessons SET {', '.join(updates)} WHERE id = ?", params)
        
        cursor.execute("SELECT * FROM memory_lessons WHERE id = ?", (lesson_id,))
        updated = dict(cursor.fetchone())
    
    return updated

@memory_router.delete("/admin/lessons/{lesson_id}")
async def delete_lesson_admin(lesson_id: str, user: dict = Depends(require_admin_auth)):
    """Delete a lesson from admin UI"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_lessons WHERE id = ?", (lesson_id,))
    
    # Also delete from vector store
    await delete_vector("memory_lessons", lesson_id)
    
    return {"message": "Deleted"}

@memory_router.get("/admin/timeline/{entity_type}/{entity_id}")
async def get_timeline_admin(
    entity_type: str,
    entity_id: str,
    user: dict = Depends(require_admin_auth)
):
    """Get timeline for admin UI (JWT auth)"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Search for entity in entities_json
        cursor.execute("""
            SELECT id, timestamp, channel, raw_text, summary_text, has_documents
            FROM memories
            WHERE entities_json LIKE ?
            ORDER BY timestamp DESC
            LIMIT 100
        """, (f'%"{entity_id}"%',))
        
        entries = []
        for row in cursor.fetchall():
            entries.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "channel": row["channel"],
                "summary_text": row["summary_text"],
                "raw_text": row["raw_text"],
                "has_documents": bool(row["has_documents"])
            })
        
        return entries

