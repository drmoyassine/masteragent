"""
memory/config.py — Memory system admin configuration endpoints

Manages entity types, subtypes, lesson types, channel types, agents,
system prompts, LLM configs, and system settings.
"""
import hashlib
import json
import logging
import secrets
import uuid
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as _BaseModel

from core.storage import get_memory_db_context
from core.utils import utcnow
from memory.auth import require_admin_auth
from services.config_helpers import get_memory_settings
from memory_models import (
    AgentCreate, AgentCreateResponse, AgentResponse,
    ChannelTypeCreate, ChannelTypeResponse,
    EntitySubtypeCreate, EntitySubtypeResponse,
    EntityTypeCreate, EntityTypeResponse,
    FetchModelsRequest, FetchModelsResponse,
    LessonTypeCreate, LessonTypeResponse,
    LLMConfigCreate, LLMConfigResponse, LLMConfigUpdate,
    MemorySettingsResponse, MemorySettingsUpdate,
    SystemPromptCreate, SystemPromptResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _list_config_table(table: str) -> list:
    """Generic helper: select all rows from a config table ordered by name."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table} ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]


# ============================================
# Admin Config Endpoints - Entity Types
# ============================================

@router.get("/config/entity-types", response_model=List[EntityTypeResponse])
async def list_entity_types(user: dict = Depends(require_admin_auth)):
    return _list_config_table("memory_entity_types")

@router.post("/config/entity-types", response_model=EntityTypeResponse)
async def create_entity_type(data: EntityTypeCreate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    type_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO memory_entity_types (id, name, description, icon, created_at) VALUES (%s, %s, %s, %s, %s)",
                (type_id, data.name, data.description, data.icon, now)
            )
        except Exception as e:
            logger.error(f"Failed to create entity type (likely duplicate): {e}")
            raise HTTPException(status_code=400, detail="Entity type already exists")
        cursor.execute("SELECT * FROM memory_entity_types WHERE id = %s", (type_id,))
        return dict(cursor.fetchone())

@router.delete("/config/entity-types/{type_id}")
async def delete_entity_type(type_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_entity_types WHERE id = %s", (type_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Entity Subtypes
# ============================================

@router.get("/config/entity-types/{type_id}/subtypes", response_model=List[EntitySubtypeResponse])
async def list_entity_subtypes(type_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_entity_subtypes WHERE entity_type_id = %s ORDER BY name", (type_id,))
        return [dict(row) for row in cursor.fetchall()]

@router.post("/config/entity-subtypes", response_model=EntitySubtypeResponse)
async def create_entity_subtype(data: EntitySubtypeCreate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    subtype_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO memory_entity_subtypes (id, entity_type_id, name, description, created_at) VALUES (%s, %s, %s, %s, %s)",
                (subtype_id, data.entity_type_id, data.name, data.description, now)
            )
        except Exception as e:
            logger.error(f"Failed to create entity subtype: {e}")
            raise HTTPException(status_code=400, detail="Subtype already exists for this entity type")
        cursor.execute("SELECT * FROM memory_entity_subtypes WHERE id = %s", (subtype_id,))
        return dict(cursor.fetchone())

@router.delete("/config/entity-subtypes/{subtype_id}")
async def delete_entity_subtype(subtype_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_entity_subtypes WHERE id = %s", (subtype_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Lesson Types
# ============================================

@router.get("/config/knowledge_types", response_model=List[LessonTypeResponse])
async def list_lesson_types(user: dict = Depends(require_admin_auth)):
    return _list_config_table("memory_lesson_types")

@router.post("/config/knowledge_types", response_model=LessonTypeResponse)
async def create_knowledge_type(data: LessonTypeCreate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    type_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO memory_lesson_types (id, name, description, color, created_at) VALUES (%s, %s, %s, %s, %s)",
                (type_id, data.name, data.description, data.color, now)
            )
        except Exception as e:
            logger.error(f"Failed to create lesson type: {e}")
            raise HTTPException(status_code=400, detail="Lesson type already exists")
        cursor.execute("SELECT * FROM memory_lesson_types WHERE id = %s", (type_id,))
        return dict(cursor.fetchone())

@router.delete("/config/knowledge_types/{type_id}")
async def delete_knowledge_type(type_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_lesson_types WHERE id = %s", (type_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Channel Types
# ============================================

@router.get("/config/channel-types", response_model=List[ChannelTypeResponse])
async def list_channel_types(user: dict = Depends(require_admin_auth)):
    return _list_config_table("memory_channel_types")

@router.post("/config/channel-types", response_model=ChannelTypeResponse)
async def create_channel_type(data: ChannelTypeCreate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    type_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO memory_channel_types (id, name, description, icon, created_at) VALUES (%s, %s, %s, %s, %s)",
                (type_id, data.name, data.description, data.icon, now)
            )
        except Exception as e:
            logger.error(f"Failed to create channel type: {e}")
            raise HTTPException(status_code=400, detail="Channel type already exists")
        cursor.execute("SELECT * FROM memory_channel_types WHERE id = %s", (type_id,))
        return dict(cursor.fetchone())

@router.delete("/config/channel-types/{type_id}")
async def delete_channel_type(type_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_channel_types WHERE id = %s", (type_id,))
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

@router.post("/config/agents")
async def create_agent(data: AgentCreate, user: dict = Depends(require_admin_auth)):
    import traceback
    now = utcnow()
    agent_id = str(uuid.uuid4())
    api_key = f"mem_{secrets.token_urlsafe(32)}"
    api_key_preview = f"{api_key[:7]}...{api_key[-4:]}"
    hashed_key = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO memory_agents (id, name, description, api_key_hash, api_key_preview, access_level, is_active, created_at) VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)",
                (agent_id, data.name, data.description, hashed_key, api_key_preview, data.access_level, now)
            )
        return {
            "id": agent_id, "name": data.name, "description": data.description,
            "api_key": api_key, "api_key_preview": api_key_preview,
            "access_level": data.access_level, "is_active": True,
            "created_at": now, "last_used": None
        }
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"create_agent FAILED: {type(e).__name__}: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")

@router.patch("/config/agents/{agent_id}")
async def update_agent(agent_id: str, user: dict = Depends(require_admin_auth), is_active: bool = None, access_level: str = None):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        updates, params = [], []
        if is_active is not None:
            updates.append("is_active = %s")
            params.append(bool(is_active))
        if access_level is not None:
            updates.append("access_level = %s")
            params.append(access_level)
        if updates:
            params.append(agent_id)
            cursor.execute(f"UPDATE memory_agents SET {', '.join(updates)} WHERE id = %s", params)
    return {"message": "Updated"}

@router.delete("/config/agents/{agent_id}")
async def delete_agent(agent_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_agents WHERE id = %s", (agent_id,))
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
    now = utcnow()
    prompt_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if data.is_active:
            cursor.execute("UPDATE memory_system_prompts SET is_active = FALSE WHERE prompt_type = %s", (data.prompt_type,))
        cursor.execute(
            "INSERT INTO memory_system_prompts (id, prompt_type, name, prompt_text, is_active, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (prompt_id, data.prompt_type, data.name, data.prompt_text, bool(data.is_active), now, now)
        )
        cursor.execute("SELECT * FROM memory_system_prompts WHERE id = %s", (prompt_id,))
        result = dict(cursor.fetchone())
        result["is_active"] = bool(result["is_active"])
        return result

@router.put("/config/system-prompts/{prompt_id}", response_model=SystemPromptResponse)
async def update_system_prompt(prompt_id: str, data: SystemPromptCreate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT prompt_type FROM memory_system_prompts WHERE id = %s", (prompt_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Prompt not found")
        if data.is_active:
            cursor.execute("UPDATE memory_system_prompts SET is_active = FALSE WHERE prompt_type = %s AND id != %s", (data.prompt_type, prompt_id))
        cursor.execute(
            "UPDATE memory_system_prompts SET prompt_type = %s, name = %s, prompt_text = %s, is_active = %s, updated_at = %s WHERE id = %s",
            (data.prompt_type, data.name, data.prompt_text, bool(data.is_active), now, prompt_id)
        )
        cursor.execute("SELECT * FROM memory_system_prompts WHERE id = %s", (prompt_id,))
        result = dict(cursor.fetchone())
        result["is_active"] = bool(result["is_active"])
        return result

@router.delete("/config/system-prompts/{prompt_id}")
async def delete_system_prompt(prompt_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_system_prompts WHERE id = %s", (prompt_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - LLM Providers
# ============================================

from memory_models import LLMProviderCreate, LLMProviderResponse, LLMProviderUpdate

@router.get("/config/llm-providers", response_model=List[LLMProviderResponse])
async def list_llm_providers(user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_providers ORDER BY created_at DESC")
        providers = []
        for row in cursor.fetchall():
            provider = dict(row)
            providers.append(LLMProviderResponse(
                id=provider["id"], name=provider["name"], provider=provider["provider"],
                api_base_url=provider.get("api_base_url", ""), api_key_preview=provider.get("api_key_preview", ""),
                rate_limit_rpm=provider.get("rate_limit_rpm", 60),
                max_retries=provider.get("max_retries", 3),
                retry_delay_ms=provider.get("retry_delay_ms", 1000),
                created_at=provider["created_at"], updated_at=provider["updated_at"]
            ))
        return providers

@router.post("/config/llm-providers", response_model=LLMProviderResponse)
async def create_llm_provider(data: LLMProviderCreate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    provider_id = str(uuid.uuid4())
    api_key_preview = f"{data.api_key[:4]}...{data.api_key[-4:]}" if data.api_key and len(data.api_key) > 8 else ("****" if data.api_key else "")
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO memory_llm_providers (id, name, provider, api_base_url, api_key_encrypted, api_key_preview, rate_limit_rpm, max_retries, retry_delay_ms, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (provider_id, data.name, data.provider, data.api_base_url or "", data.api_key or "", api_key_preview, data.rate_limit_rpm, data.max_retries, data.retry_delay_ms, now, now)
        )
        return LLMProviderResponse(
            id=provider_id, name=data.name, provider=data.provider,
            api_base_url=data.api_base_url or "", api_key_preview=api_key_preview,
            rate_limit_rpm=data.rate_limit_rpm, max_retries=data.max_retries, retry_delay_ms=data.retry_delay_ms,
            created_at=now, updated_at=now
        )

@router.put("/config/llm-providers/{provider_id}", response_model=LLMProviderResponse)
async def update_llm_provider(provider_id: str, data: LLMProviderUpdate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_providers WHERE id = %s", (provider_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="LLM provider not found")
        updates, params = ["updated_at = %s"], [now]
        if data.name is not None:
            updates.append("name = %s"); params.append(data.name)
        if data.provider is not None:
            updates.append("provider = %s"); params.append(data.provider)
        if data.api_base_url is not None:
            updates.append("api_base_url = %s"); params.append(data.api_base_url)
        if data.api_key is not None:
            updates.append("api_key_encrypted = %s"); params.append(data.api_key)
            api_key_preview = f"{data.api_key[:4]}...{data.api_key[-4:]}" if len(data.api_key) > 8 else "****"
            updates.append("api_key_preview = %s"); params.append(api_key_preview)
        if data.rate_limit_rpm is not None:
            updates.append("rate_limit_rpm = %s"); params.append(data.rate_limit_rpm)
        if data.max_retries is not None:
            updates.append("max_retries = %s"); params.append(data.max_retries)
        if data.retry_delay_ms is not None:
            updates.append("retry_delay_ms = %s"); params.append(data.retry_delay_ms)
            
        params.append(provider_id)
        cursor.execute(f"UPDATE memory_llm_providers SET {', '.join(updates)} WHERE id = %s", params)
        cursor.execute("SELECT * FROM memory_llm_providers WHERE id = %s", (provider_id,))
        updated = dict(cursor.fetchone())
        return LLMProviderResponse(
            id=updated["id"], name=updated["name"], provider=updated["provider"],
            api_base_url=updated.get("api_base_url", ""), api_key_preview=updated.get("api_key_preview", ""),
            rate_limit_rpm=updated.get("rate_limit_rpm", 60),
            max_retries=updated.get("max_retries", 3),
            retry_delay_ms=updated.get("retry_delay_ms", 1000),
            created_at=updated["created_at"], updated_at=updated["updated_at"]
        )

@router.delete("/config/llm-providers/{provider_id}")
async def delete_llm_provider(provider_id: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_llm_providers WHERE id = %s", (provider_id,))
    return {"message": "Deleted"}

@router.post("/config/llm-providers/test")
async def test_llm_provider(data: FetchModelsRequest, user: dict = Depends(require_admin_auth)):
    return await fetch_provider_models(data, user)

# ============================================
# Admin Config Endpoints - LLM Configurations
# ============================================

@router.get("/config/llm-configs", response_model=List[LLMConfigResponse])
async def list_llm_configs(user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_configs ORDER BY pipeline_stage, execution_order ASC, created_at DESC")
        configs = []
        for row in cursor.fetchall():
            config = dict(row)
            configs.append(LLMConfigResponse(
                id=config["id"], task_type=config["task_type"],
                pipeline_stage=config.get("pipeline_stage"), execution_order=config.get("execution_order", 0),
                provider_id=config.get("provider_id"),
                model_name=config.get("model_name", ""), prompt_id=config.get("prompt_id"),
                inline_system_prompt=config.get("inline_system_prompt"), inline_schema=config.get("inline_schema"),
                is_active=bool(config.get("is_active", 0)),
                extra_config=json.loads(config.get("extra_config_json", "{}")),
                created_at=config["created_at"], updated_at=config["updated_at"]
            ))
        return configs

@router.get("/config/llm-configs/{task_type}", response_model=LLMConfigResponse)
async def get_llm_config_by_task(task_type: str, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_configs WHERE task_type = %s AND is_active = TRUE ORDER BY updated_at DESC LIMIT 1", (task_type,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No active LLM config for {task_type}")
        config = dict(row)
        return LLMConfigResponse(
            id=config["id"], task_type=config["task_type"],
            pipeline_stage=config.get("pipeline_stage"), execution_order=config.get("execution_order", 0),
            provider_id=config.get("provider_id"),
            model_name=config.get("model_name", ""), prompt_id=config.get("prompt_id"),
            inline_system_prompt=config.get("inline_system_prompt"), inline_schema=config.get("inline_schema"),
            is_active=bool(config.get("is_active", 0)),
            extra_config=json.loads(config.get("extra_config_json", "{}")),
            created_at=config["created_at"], updated_at=config["updated_at"]
        )

@router.post("/config/llm-configs", response_model=LLMConfigResponse)
async def create_llm_config(data: LLMConfigCreate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    config_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        # Deprecated: uniqueness on active task_type removed
        cursor.execute(
            "INSERT INTO memory_llm_configs (id, task_type, pipeline_stage, execution_order, provider_id, model_name, is_active, extra_config_json, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (config_id, data.task_type, data.pipeline_stage, data.execution_order, data.provider_id, data.model_name or "", bool(data.is_active), json.dumps(data.extra_config or {}), now, now)
        )
        return LLMConfigResponse(
            id=config_id, task_type=data.task_type, pipeline_stage=data.pipeline_stage, execution_order=data.execution_order,
            provider_id=data.provider_id, model_name=data.model_name or "",
            is_active=data.is_active, extra_config=data.extra_config or {},
            created_at=now, updated_at=now
        )

@router.put("/config/llm-configs/{config_id}", response_model=LLMConfigResponse)
async def update_llm_config(config_id: str, data: LLMConfigUpdate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_llm_configs WHERE id = %s", (config_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="LLM config not found")
        existing = dict(existing)
        updates, params = ["updated_at = %s"], [now]
        if data.pipeline_stage is not None:
            updates.append("pipeline_stage = %s"); params.append(data.pipeline_stage)
        if data.execution_order is not None:
            updates.append("execution_order = %s"); params.append(data.execution_order)
        if data.provider_id is not None:
            updates.append("provider_id = %s"); params.append(data.provider_id)
        if data.model_name is not None:
            updates.append("model_name = %s"); params.append(data.model_name)
        if data.prompt_id is not None:
            # If changing from linked to inline or vice-versa, handle nulling empty strings
            val = data.prompt_id if data.prompt_id.strip() else None
            updates.append("prompt_id = %s"); params.append(val)
        if data.inline_system_prompt is not None:
            updates.append("inline_system_prompt = %s"); params.append(data.inline_system_prompt)
        if data.inline_schema is not None:
            updates.append("inline_schema = %s"); params.append(data.inline_schema)
        if data.is_active is not None:
            # Deprecated: uniqueness on active task_type removed
            updates.append("is_active = %s"); params.append(bool(data.is_active))
        if data.extra_config is not None:
            updates.append("extra_config_json = %s"); params.append(json.dumps(data.extra_config))
        params.append(config_id)
        cursor.execute(f"UPDATE memory_llm_configs SET {', '.join(updates)} WHERE id = %s", params)
        cursor.execute("SELECT * FROM memory_llm_configs WHERE id = %s", (config_id,))
        updated = dict(cursor.fetchone())
        return LLMConfigResponse(
            id=updated["id"], task_type=updated["task_type"],
            pipeline_stage=updated.get("pipeline_stage"), execution_order=updated.get("execution_order", 0),
            provider_id=updated.get("provider_id"),
            model_name=updated.get("model_name", ""), prompt_id=updated.get("prompt_id"),
            inline_system_prompt=updated.get("inline_system_prompt"), inline_schema=updated.get("inline_schema"),
            is_active=bool(updated.get("is_active", 0)),
            extra_config=json.loads(updated.get("extra_config_json", "{}")),
            created_at=updated["created_at"], updated_at=updated["updated_at"]
        )

from memory_models import PipelineReorderRequest

@router.patch("/config/llm-configs/reorder")
async def reorder_pipeline_nodes(data: PipelineReorderRequest, user: dict = Depends(require_admin_auth)):
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        for idx, config_id in enumerate(data.ordered_ids):
            cursor.execute(
                "UPDATE memory_llm_configs SET execution_order = %s, pipeline_stage = %s WHERE id = %s",
                (idx, data.pipeline_stage, config_id)
            )
    return {"message": "Reordered successfully"}

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

    # If missing api_key OR missing api_base_url, try to fetch from DB
    if (not api_key or not api_base_url) and data.provider_id:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT api_key_encrypted, api_base_url FROM memory_llm_providers WHERE id = %s", (data.provider_id,))
            row = cursor.fetchone()
            if row:
                if not api_key and row["api_key_encrypted"]:
                    api_key = row["api_key_encrypted"]
                if not api_base_url and row["api_base_url"]:
                    api_base_url = row["api_base_url"].rstrip("/")

    # Final check: do we have a key? (except for Ollama which might be local)
    if not api_key and provider != "ollama":
        raise HTTPException(
            status_code=401, 
            detail=f"No API key found for {provider}. Please enter a key or ensure it is configured in another task category."
        )

    models: List[str] = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
                if base.endswith("/v1"):
                    base = base[:-3]
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
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Timeout connecting to {provider} endpoint. Try increasing timeout or check network.")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Cannot connect to {provider} endpoint. Check the base URL and ensure the service is running.")
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
        cursor.execute("DELETE FROM memory_llm_configs WHERE id = %s", (config_id,))
    return {"message": "Deleted"}


# ============================================
# Admin Config Endpoints - Settings
# ============================================

@router.get("/config/settings", response_model=MemorySettingsResponse)
async def get_settings_endpoint(user: dict = Depends(require_admin_auth)):
    settings = get_memory_settings()
    return MemorySettingsResponse(
        chunk_size=settings.get("chunk_size", 400), chunk_overlap=settings.get("chunk_overlap", 80),
        memory_generation_time=settings.get("memory_generation_time", "02:00"),
        memory_generation_mode=settings.get("memory_generation_mode", "ner_and_raw"),
        auto_public_knowledge_enabled=bool(settings.get("auto_public_knowledge_enabled", 1)), auto_knowledge_threshold=settings.get("auto_knowledge_threshold", 5),
        knowledge_threshold=settings.get("knowledge_threshold", 5), intelligence_extraction_threshold=settings.get("intelligence_extraction_threshold", 10),
        pii_scrubbing_enabled=bool(settings.get("pii_scrubbing_enabled", 1)),
        auto_share_scrubbed=bool(settings.get("auto_share_scrubbed", 0)), rate_limit_enabled=bool(settings.get("rate_limit_enabled", 0)),
        rate_limit_per_minute=settings.get("rate_limit_per_minute", 60), default_agent_access=settings.get("default_agent_access", "private")
    )

@router.put("/config/settings", response_model=MemorySettingsResponse)
async def update_settings_endpoint(data: MemorySettingsUpdate, user: dict = Depends(require_admin_auth)):
    now = utcnow()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        updates, params = [], []
        for field, value in data.dict(exclude_unset=True).items():
            if value is not None:
                updates.append(f"{field} = %s"); params.append(value)
        if updates:
            updates.append("updated_at = %s"); params.append(now)
            cursor.execute(f"UPDATE memory_settings SET {', '.join(updates)} WHERE id = 1", params)
    return await get_settings_endpoint(user)


# ============================================
# Supabase Connection Endpoints
# ============================================

class SupabaseConnectRequest(_BaseModel):
    supabase_url: str           # https://xyz.supabase.co
    supabase_db_url: str        # postgresql://postgres:<pw>@db.xyz.supabase.co:5432/postgres


@router.post("/config/supabase/connect")
async def connect_supabase_endpoint(
    body: SupabaseConnectRequest,
    user: dict = Depends(require_admin_auth)
):
    """
    Connect a Supabase project as the memory storage backend.
    Validates the connection, writes credentials to memory_settings,
    and switches the storage layer to use Supabase PostgreSQL.
    """
    from core.storage import connect_supabase
    result = connect_supabase(body.supabase_url, body.supabase_db_url)
    if not result.get("connected"):
        raise HTTPException(status_code=400, detail=result.get("error", "Connection failed"))
    return result


@router.get("/config/supabase/status")
async def get_supabase_status_endpoint(user: dict = Depends(require_admin_auth)):
    """Return the current storage backend status (local or Supabase)."""
    from core.storage import get_supabase_status
    return get_supabase_status()


@router.delete("/config/supabase/connect")
async def disconnect_supabase_endpoint(user: dict = Depends(require_admin_auth)):
    """
    Disconnect from Supabase — revert to local PostgreSQL.
    Clears supabase_url and supabase_db_url from memory_settings.
    """
    from core.storage import disconnect_supabase
    result = disconnect_supabase()
    if not result.get("disconnected"):
        raise HTTPException(status_code=500, detail=result.get("error", "Disconnect failed"))
    return result

