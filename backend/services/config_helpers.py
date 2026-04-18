"""services/config_helpers.py — DB-backed config lookups"""
import json
import logging
from typing import Any, Dict, List, Optional

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


def get_memory_settings() -> Dict[str, Any]:
    """Get current memory settings (singleton row)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_settings WHERE id = 1")
        row = cursor.fetchone()
        return dict(row) if row else {}


def _parse_extra_config(config: dict) -> dict:
    """Parse extra_config_json field into config dict (DRY helper)."""
    extra = config.get("extra_config_json") or "{}"
    if isinstance(extra, str):
        try:
            config["extra_config"] = json.loads(extra)
        except Exception:
            config["extra_config"] = {}
    else:
        config["extra_config"] = extra
    return config


def get_llm_config(task_type: str) -> Optional[Dict[str, Any]]:
    """
    Get active LLM configuration for a task type by joining with the provider table.
    Returns the first active config ordered by execution_order (pipeline-aware).
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, p.provider, p.api_base_url, p.api_key_encrypted 
            FROM memory_llm_configs c
            LEFT JOIN memory_llm_providers p ON c.provider_id = p.id
            WHERE c.task_type = %s AND c.is_active = TRUE
            ORDER BY c.execution_order ASC LIMIT 1
        """, (task_type,))
        row = cursor.fetchone()
        if not row:
            return None
        return _parse_extra_config(dict(row))


def get_llm_config_by_id(config_id: str) -> Optional[Dict[str, Any]]:
    """
    Get LLM configuration by its exact ID (active or not — used for pipeline execution).
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, p.provider, p.api_base_url, p.api_key_encrypted 
            FROM memory_llm_configs c
            LEFT JOIN memory_llm_providers p ON c.provider_id = p.id
            WHERE c.id = %s
        """, (config_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return _parse_extra_config(dict(row))


def get_pipeline_configs(pipeline_stage: str) -> List[Dict[str, Any]]:
    """
    Fetch ALL active LLM configs for a pipeline stage, ordered by execution_order.
    This is the primary driver for the sequential pipeline executor.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, p.provider, p.api_base_url, p.api_key_encrypted 
            FROM memory_llm_configs c
            LEFT JOIN memory_llm_providers p ON c.provider_id = p.id
            WHERE c.pipeline_stage = %s AND c.is_active = TRUE
            ORDER BY c.execution_order ASC
        """, (pipeline_stage,))
        return [_parse_extra_config(dict(row)) for row in cursor.fetchall()]


def get_system_prompt_by_config_id(config_id: str) -> Optional[str]:
    """Get the system prompt for a specific config node by its ID.
    Resolution: inline_system_prompt → linked prompt_id → memory_system_prompts fallback."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_type, prompt_id, inline_system_prompt FROM memory_llm_configs
            WHERE id = %s
        """, (config_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        inline_prompt = row.get("inline_system_prompt")
        prompt_id = row.get("prompt_id")
        task_type = row.get("task_type")
    
    # Priority 1: inline prompt on the config row
    if inline_prompt and inline_prompt.strip():
        return inline_prompt
    
    # Priority 2: linked Prompt Manager template
    if prompt_id:
        try:
            from storage_service import get_storage_service
            storage = get_storage_service("default")
            import asyncio
            prompt_data = asyncio.get_event_loop().run_until_complete(
                storage.get_prompt_content(f"prompts/{prompt_id}", "v1")
            )
            if prompt_data:
                return "\n\n".join(s.get("content", "") for s in prompt_data.get("sections", []))
        except Exception as e:
            logger.error(f"Error fetching prompt {prompt_id}: {e}")
    
    # Priority 3: legacy memory_system_prompts table
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT prompt_text FROM memory_system_prompts
            WHERE prompt_type = %s AND is_active = TRUE
            ORDER BY updated_at DESC LIMIT 1
        """, (task_type,))
        row = cursor.fetchone()
        return row["prompt_text"] if row else None


def get_schema_by_config_id(config_id: str) -> Optional[str]:
    """Get the inline_schema for a specific config node by its ID."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT inline_schema FROM memory_llm_configs WHERE id = %s", (config_id,))
        row = cursor.fetchone()
        if row and row.get("inline_schema"):
            return row["inline_schema"]
    return None


async def get_system_prompt(task_type: str, user_id: str = "default") -> Optional[str]:
    """Get active system prompt text by fetching the linked Prompt Manager entry."""
    
    # 2. Extract values
    prompt_id = None
    inline_prompt = None
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT prompt_id, inline_system_prompt FROM memory_llm_configs
            WHERE task_type = %s AND is_active = TRUE
            ORDER BY updated_at DESC LIMIT 1
        """, (task_type,))
        row = cursor.fetchone()
        if row:
            prompt_id = row.get("prompt_id")
            inline_prompt = row.get("inline_system_prompt")
            
    # 3. If a PromptManager template is NOT linked, return the inline one or fallback.
    if not prompt_id:
        if inline_prompt and inline_prompt.strip():
            return inline_prompt
            
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT prompt_text FROM memory_system_prompts
                WHERE prompt_type = %s AND is_active = TRUE
                ORDER BY updated_at DESC LIMIT 1
            """, (task_type,))
            row = cursor.fetchone()
            return row["prompt_text"] if row else None
            
    # 4. Try fetching from Prompt Manager storage
    try:
        from storage_service import get_storage_service
        storage = get_storage_service(user_id)
        
        # We need the folder_path for this prompt_id
        folder_path = f"prompts/{prompt_id}"
        
        # We don't render variables here; we just want the raw template
        # The variables will be injected by the pipeline using prompt_renderer logic
        prompt_data = await storage.get_prompt_content(folder_path, "v1")
        if not prompt_data:
            return None
            
        rendered = []
        for section in prompt_data.get("sections", []):
            rendered.append(section.get("content", ""))
            
        return "\n\n".join(rendered)
        
    except Exception as e:
        logger.error(f"Error fetching prompt {prompt_id} for task {task_type}: {e}")
        return None

async def get_schema(task_type: str) -> Optional[str]:
    """Retrieve the inline schema for a task type if defined."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT inline_schema FROM memory_llm_configs
            WHERE task_type = %s AND is_active = TRUE
            ORDER BY updated_at DESC LIMIT 1
        """, (task_type,))
        row = cursor.fetchone()
        if row and row.get("inline_schema"):
            return row["inline_schema"]
    return None
