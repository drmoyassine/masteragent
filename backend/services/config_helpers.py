"""services/config_helpers.py — DB-backed config lookups"""
import json
import logging
from typing import Any, Dict, Optional

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


def get_memory_settings() -> Dict[str, Any]:
    """Get current memory settings (singleton row)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_settings WHERE id = 1")
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_llm_config(task_type: str) -> Optional[Dict[str, Any]]:
    """
    Get active LLM configuration for a task type by joining with the provider table.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, p.provider, p.api_base_url, p.api_key_encrypted 
            FROM memory_llm_configs c
            LEFT JOIN memory_llm_providers p ON c.provider_id = p.id
            WHERE c.task_type = %s AND c.is_active = TRUE
            ORDER BY c.updated_at DESC LIMIT 1
        """, (task_type,))
        row = cursor.fetchone()
        if not row:
            return None

        config = dict(row)
        extra = config.get("extra_config_json") or "{}"
        if isinstance(extra, str):
            try:
                config["extra_config"] = json.loads(extra)
            except Exception:
                config["extra_config"] = {}
        else:
            config["extra_config"] = extra

        return config


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
