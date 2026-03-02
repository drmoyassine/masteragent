"""
memory/config.py — Memory system admin configurations

Handles creating and managing entity types, subtypes, lesson types, 
channel types, agents, system prompts, LLM configs, and system settings.
"""
import json
import secrets
import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Optional
import logging
import httpx

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException

from memory_db import get_memory_db_context
from memory_models import (
    AgentCreate, AgentCreateResponse, AgentResponse,
    ChannelTypeCreate, ChannelTypeResponse,
    EntitySubtypeCreate, EntitySubtypeResponse,
    EntityTypeCreate, EntityTypeResponse,
    LessonTypeCreate, LessonTypeResponse,
    LLMConfigCreate, LLMConfigResponse, LLMConfigUpdate,
    FetchModelsRequest, FetchModelsResponse,
    MemorySettingsResponse, MemorySettingsUpdate,
    SystemPromptCreate, SystemPromptResponse
)
from memory_services import get_memory_settings
from memory.auth import require_admin_auth

router = APIRouter()


# ============================================
# Admin Config Endpoints - Entity Types
# ============================================

@router.get("/config/entity-types", response_model=List[EntityTypeResponse])
async def list_entity_types(user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_entity_types ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

@router.post("/config/entity-types", response_model=EntityTypeResponse)
async def create_entity_type(data: EntityTypeCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    type_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO memory_entity_types (id, name, description, icon, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (type_id, data.name, data.description, data.icon, now, now)
            )
        except Exception as e:
            logger.error(f"Failed to create entity type (likely duplicate): {e}")
            raise HTTPException(status_code=400, detail="Entity type already exists")
        cursor.execute("SELECT * FROM memory_entity_types WHERE id = ?", (type_id,))
        return dict(cursor.fetchone())

@router.delete("/config/entity-types/{type_id}")
async def delete_entity_type(type_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_entity_types WHERE id = ?", (type_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Entity Subtypes
# ============================================

@router.get("/config/entity-types/{type_id}/subtypes", response_model=List[EntitySubtypeResponse])
async def list_entity_subtypes(type_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_entity_subtypes WHERE entity_type_id = ? ORDER BY name", (type_id,))
        return [dict(row) for row in cursor.fetchall()]

@router.post("/config/entity-subtypes", response_model=EntitySubtypeResponse)
async def create_entity_subtype(data: EntitySubtypeCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    subtype_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO memory_entity_subtypes (id, entity_type_id, name, description, created_at) VALUES (?, ?, ?, ?, ?)",
                (subtype_id, data.entity_type_id, data.name, data.description, now)
            )
        except Exception as e:
            logger.error(f"Failed to create entity subtype: {e}")
            raise HTTPException(status_code=400, detail="Subtype already exists for this entity type")
        cursor.execute("SELECT * FROM memory_entity_subtypes WHERE id = ?", (subtype_id,))
        return dict(cursor.fetchone())

@router.delete("/config/entity-subtypes/{subtype_id}")
async def delete_entity_subtype(subtype_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_entity_subtypes WHERE id = ?", (subtype_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Lesson Types
# ============================================

@router.get("/config/lesson-types", response_model=List[LessonTypeResponse])
async def list_lesson_types(user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_lesson_types ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

@router.post("/config/lesson-types", response_model=LessonTypeResponse)
async def create_lesson_type(data: LessonTypeCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    type_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO memory_lesson_types (id, name, description, color, created_at) VALUES (?, ?, ?, ?, ?)",
                (type_id, data.name, data.description, data.color, now)
            )
        except Exception as e:
            logger.error(f"Failed to create lesson type: {e}")
            raise HTTPException(status_code=400, detail="Lesson type already exists")
        cursor.execute("SELECT * FROM memory_lesson_types WHERE id = ?", (type_id,))
        return dict(cursor.fetchone())

@router.delete("/config/lesson-types/{type_id}")
async def delete_lesson_type(type_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_lesson_types WHERE id = ?", (type_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Channel Types
# ============================================

@router.get("/config/channel-types", response_model=List[ChannelTypeResponse])
async def list_channel_types(user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_channel_types ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

@router.post("/config/channel-types", response_model=ChannelTypeResponse)
async def create_channel_type(data: ChannelTypeCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    type_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO memory_channel_types (id, name, description, icon, created_at) VALUES (?, ?, ?, ?, ?)",
                (type_id, data.name, data.description, data.icon, now)
            )
        except Exception as e:
            logger.error(f"Failed to create channel type: {e}")
            raise HTTPException(status_code=400, detail="Channel type already exists")
        cursor.execute("SELECT * FROM memory_channel_types WHERE id = ?", (type_id,))
        return dict(cursor.fetchone())

@router.delete("/config/channel-types/{type_id}")
async def delete_channel_type(type_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_channel_types WHERE id = ?", (type_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Agents
# ============================================

@router.get("/config/agents", response_model=List[AgentResponse])
async def list_agents(user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_agents ORDER BY created_at DESC")
        agents = []
        for row in cursor.fetchall():
            agent = dict(row)
            agent["is_active"] = bool(agent["is_active"])
            agents.append(agent)
        return agents

@router.post("/config/agents", response_model=AgentCreateResponse)
async def create_agent(data: AgentCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    agent_id = str(uuid.uuid4())
    api_key = f"mem_{secrets.token_urlsafe(32)}"
    api_key_preview = f"{api_key[:7]}...{api_key[-4:]}"
    hashed_key = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO memory_agents (id, name, description, api_key_hash, api_key_preview, access_level, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (agent_id, data.name, data.description, hashed_key, api_key_preview, data.access_level, now)
        )
        return AgentCreateResponse(
            id=agent_id, name=data.name, description=data.description,
            api_key=api_key, api_key_preview=api_key_preview,
            access_level=data.access_level, is_active=True, created_at=now, last_used=None
        )

@router.patch("/config/agents/{agent_id}")
async def update_agent(agent_id: str, user: dict = Depends(require_admin_auth), is_active: bool = None, access_level: str = None):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        updates, params = [], []
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

@router.delete("/config/agents/{agent_id}")
async def delete_agent(agent_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_agents WHERE id = ?", (agent_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - System Prompts
# ============================================

@router.get("/config/system-prompts", response_model=List[SystemPromptResponse])
async def list_system_prompts(user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_system_prompts ORDER BY prompt_type, created_at DESC")
        prompts = []
        for row in cursor.fetchall():
            prompt = dict(row)
            prompt["is_active"] = bool(prompt["is_active"])
            prompts.append(prompt)
        return prompts

@router.post("/config/system-prompts", response_model=SystemPromptResponse)
async def create_system_prompt(data: SystemPromptCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    prompt_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if data.is_active:
            cursor.execute("UPDATE memory_system_prompts SET is_active = 0 WHERE prompt_type = ?", (data.prompt_type,))
        cursor.execute(
            "INSERT INTO memory_system_prompts (id, prompt_type, name, prompt_text, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (prompt_id, data.prompt_type, data.name, data.prompt_text, 1 if data.is_active else 0, now, now)
        )
        cursor.execute("SELECT * FROM memory_system_prompts WHERE id = ?", (prompt_id,))
        result = dict(cursor.fetchone())
        result["is_active"] = bool(result["is_active"])
        return result

@router.put("/config/system-prompts/{prompt_id}", response_model=SystemPromptResponse)
async def update_system_prompt(prompt_id: str, data: SystemPromptCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT prompt_type FROM memory_system_prompts WHERE id = ?", (prompt_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Prompt not found")
        if data.is_active:
            cursor.execute("UPDATE memory_system_prompts SET is_active = 0 WHERE prompt_type = ? AND id != ?", (data.prompt_type, prompt_id))
        cursor.execute(
            "UPDATE memory_system_prompts SET prompt_type = ?, name = ?, prompt_text = ?, is_active = ?, updated_at = ? WHERE id = ?",
            (data.prompt_type, data.name, data.prompt_text, 1 if data.is_active else 0, now, prompt_id)
        )
        cursor.execute("SELECT * FROM memory_system_prompts WHERE id = ?", (prompt_id,))
        result = dict(cursor.fetchone())
        result["is_active"] = bool(result["is_active"])
        return result

@router.delete("/config/system-prompts/{prompt_id}")
async def delete_system_prompt(prompt_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_system_prompts WHERE id = ?", (prompt_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - LLM Configurations
# ============================================

@router.get("/config/llm-configs", response_model=List[LLMConfigResponse])
async def list_llm_configs(user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_configs ORDER BY task_type, created_at DESC")
        configs = []
        for row in cursor.fetchall():
            config = dict(row)
            configs.append(LLMConfigResponse(
                id=config["id"], task_type=config["task_type"], provider=config["provider"], name=config["name"],
                api_base_url=config.get("api_base_url", ""), api_key_preview=config.get("api_key_preview", ""),
                model_name=config.get("model_name", ""), is_active=bool(config.get("is_active", 0)),
                extra_config=json.loads(config.get("extra_config_json", "{}")),
                created_at=config["created_at"], updated_at=config["updated_at"]
            ))
        return configs

@router.get("/config/llm-configs/{task_type}", response_model=LLMConfigResponse)
async def get_llm_config_by_task(task_type: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_configs WHERE task_type = ? AND is_active = 1 ORDER BY updated_at DESC LIMIT 1", (task_type,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No active LLM config for {task_type}")
        config = dict(row)
        return LLMConfigResponse(
            id=config["id"], task_type=config["task_type"], provider=config["provider"], name=config["name"],
            api_base_url=config.get("api_base_url", ""), api_key_preview=config.get("api_key_preview", ""),
            model_name=config.get("model_name", ""), is_active=bool(config.get("is_active", 0)),
            extra_config=json.loads(config.get("extra_config_json", "{}")),
            created_at=config["created_at"], updated_at=config["updated_at"]
        )

@router.post("/config/llm-configs", response_model=LLMConfigResponse)
async def create_llm_config(data: LLMConfigCreate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    config_id = str(uuid.uuid4())
    api_key_preview = f"{data.api_key[:4]}...{data.api_key[-4:]}" if data.api_key and len(data.api_key) > 8 else ("****" if data.api_key else "")
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if data.is_active:
            cursor.execute("UPDATE memory_llm_configs SET is_active = 0 WHERE task_type = ?", (data.task_type,))
        cursor.execute(
            "INSERT INTO memory_llm_configs (id, task_type, provider, name, api_base_url, api_key_encrypted, api_key_preview, model_name, is_active, extra_config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (config_id, data.task_type, data.provider, data.name, data.api_base_url or "", data.api_key or "", api_key_preview, data.model_name or "", 1 if data.is_active else 0, json.dumps(data.extra_config or {}), now, now)
        )
        return LLMConfigResponse(
            id=config_id, task_type=data.task_type, provider=data.provider, name=data.name,
            api_base_url=data.api_base_url or "", api_key_preview=api_key_preview, model_name=data.model_name or "",
            is_active=data.is_active, extra_config=data.extra_config or {},
            created_at=now, updated_at=now
        )

@router.put("/config/llm-configs/{config_id}", response_model=LLMConfigResponse)
async def update_llm_config(config_id: str, data: LLMConfigUpdate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_configs WHERE id = ?", (config_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="LLM config not found")
        existing = dict(existing)
        updates, params = ["updated_at = ?"], [now]
        if data.name is not None:
            updates.append("name = ?"); params.append(data.name)
        if data.api_base_url is not None:
            updates.append("api_base_url = ?"); params.append(data.api_base_url)
        if data.api_key is not None:
            updates.append("api_key_encrypted = ?"); params.append(data.api_key)
            api_key_preview = f"{data.api_key[:4]}...{data.api_key[-4:]}" if len(data.api_key) > 8 else "****"
            updates.append("api_key_preview = ?"); params.append(api_key_preview)
        if data.model_name is not None:
            updates.append("model_name = ?"); params.append(data.model_name)
        if data.is_active is not None:
            if data.is_active:
                cursor.execute("UPDATE memory_llm_configs SET is_active = 0 WHERE task_type = ? AND id != ?", (existing["task_type"], config_id))
            updates.append("is_active = ?"); params.append(1 if data.is_active else 0)
        if data.extra_config is not None:
            updates.append("extra_config_json = ?"); params.append(json.dumps(data.extra_config))
        params.append(config_id)
        cursor.execute(f"UPDATE memory_llm_configs SET {', '.join(updates)} WHERE id = ?", params)
        cursor.execute("SELECT * FROM memory_llm_configs WHERE id = ?", (config_id,))
        updated = dict(cursor.fetchone())
        return LLMConfigResponse(
            id=updated["id"], task_type=updated["task_type"], provider=updated["provider"], name=updated["name"],
            api_base_url=updated.get("api_base_url", ""), api_key_preview=updated.get("api_key_preview", ""),
            model_name=updated.get("model_name", ""), is_active=bool(updated.get("is_active", 0)),
            extra_config=json.loads(updated.get("extra_config_json", "{}")),
            created_at=updated["created_at"], updated_at=updated["updated_at"]
        )

@router.post("/config/llm-configs/fetch-models", response_model=FetchModelsResponse)
async def fetch_provider_models(data: FetchModelsRequest, user: dict = Depends(require_admin_auth)):
    """
    Proxy endpoint that fetches available models from a provider's API.
    Keeps API keys server-side and avoids browser CORS issues.
    If api_key is not provided but config_id is, falls back to the stored key.
    """
    provider = data.provider.lower()
    api_key = data.api_key or ""
    api_base_url = (data.api_base_url or "").rstrip("/")

    # If no key was supplied (e.g. user re-opened edit panel without re-entering key),
    # fall back to the stored encrypted key from the database.
    if not api_key and data.config_id:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT api_key_encrypted, api_base_url FROM memory_llm_configs WHERE id = ?", (data.config_id,))
            row = cursor.fetchone()
            if row:
                api_key = row["api_key_encrypted"] or ""
                if not api_base_url and row["api_base_url"]:
                    api_base_url = row["api_base_url"].rstrip("/")

    models: List[str] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if provider == "openai":
                base = api_base_url or "https://api.openai.com/v1"
                resp = await client.get(
                    f"{base}/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                resp.raise_for_status()
                data_json = resp.json()
                all_ids = [m["id"] for m in data_json.get("data", [])]
                # Sort: show GPT / embedding / etc models first
                models = sorted(all_ids)

            elif provider == "gemini":
                base = api_base_url or "https://generativelanguage.googleapis.com/v1beta"
                resp = await client.get(
                    f"{base}/models",
                    params={"key": api_key}
                )
                resp.raise_for_status()
                data_json = resp.json()
                models = sorted([
                    m["name"].replace("models/", "")
                    for m in data_json.get("models", [])
                ])

            elif provider == "openrouter":
                base = api_base_url or "https://openrouter.ai/api/v1"
                resp = await client.get(
                    f"{base}/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                resp.raise_for_status()
                data_json = resp.json()
                models = sorted([m["id"] for m in data_json.get("data", [])])

            elif provider == "ollama":
                base = api_base_url or "http://localhost:11434"
                resp = await client.get(f"{base}/api/tags")
                resp.raise_for_status()
                data_json = resp.json()
                models = sorted([m["name"] for m in data_json.get("models", [])])

            elif provider == "anthropic":
                # Anthropic does not expose a public model list API — return curated static list
                models = [
                    "claude-opus-4-5",
                    "claude-sonnet-4-5",
                    "claude-haiku-4-5",
                    "claude-3-7-sonnet-20250219",
                    "claude-3-5-haiku-20241022",
                    "claude-3-opus-20240229",
                    "claude-3-sonnet-20240229",
                    "claude-3-haiku-20240307",
                ]

            else:
                raise HTTPException(status_code=400, detail=f"Provider '{provider}' does not support model fetching")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching models for {provider}: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Provider API error: {e.response.text[:200]}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Cannot connect to {provider} endpoint. Check the base URL and ensure the service is running.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Timeout connecting to {provider} endpoint.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching models for {provider}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")

    return FetchModelsResponse(models=models, provider=provider)


@router.delete("/config/llm-configs/{config_id}")
async def delete_llm_config(config_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_llm_configs WHERE id = ?", (config_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Settings
# ============================================

@router.get("/config/settings", response_model=MemorySettingsResponse)
async def get_settings_endpoint(user: dict = Depends(require_admin_auth)):
    settings = get_memory_settings()
    return MemorySettingsResponse(
        chunk_size=settings.get("chunk_size", 400), chunk_overlap=settings.get("chunk_overlap", 80),
        auto_lesson_enabled=bool(settings.get("auto_lesson_enabled", 1)), auto_lesson_threshold=settings.get("auto_lesson_threshold", 5),
        lesson_approval_required=bool(settings.get("lesson_approval_required", 1)), pii_scrubbing_enabled=bool(settings.get("pii_scrubbing_enabled", 1)),
        auto_share_scrubbed=bool(settings.get("auto_share_scrubbed", 0)), openclaw_sync_enabled=bool(settings.get("openclaw_sync_enabled", 0)),
        openclaw_sync_path=settings.get("openclaw_sync_path", ""), openclaw_sync_type=settings.get("openclaw_sync_type", "filesystem"),
        openclaw_sync_frequency=settings.get("openclaw_sync_frequency", 5), rate_limit_enabled=bool(settings.get("rate_limit_enabled", 0)),
        rate_limit_per_minute=settings.get("rate_limit_per_minute", 60), default_agent_access=settings.get("default_agent_access", "private")
    )

@router.put("/config/settings", response_model=MemorySettingsResponse)
async def update_settings_endpoint(data: MemorySettingsUpdate, user: dict = Depends(require_admin_auth)):
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        updates, params = [], []
        for field, value in data.dict(exclude_unset=True).items():
            if value is not None:
                if isinstance(value, bool): value = 1 if value else 0
                updates.append(f"{field} = ?"); params.append(value)
        if updates:
            updates.append("updated_at = ?"); params.append(now)
            cursor.execute(f"UPDATE memory_settings SET {', '.join(updates)} WHERE id = 1", params)
    return await get_settings_endpoint(user)
