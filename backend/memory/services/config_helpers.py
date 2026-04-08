"""memory/services/config_helpers.py — DB-backed config lookups"""
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


def get_system_prompt(prompt_type: str) -> Optional[str]:
    """Get active system prompt text by type."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT prompt_text FROM memory_system_prompts
            WHERE prompt_type = %s AND is_active = TRUE
            ORDER BY updated_at DESC LIMIT 1
        """, (prompt_type,))
        row = cursor.fetchone()
        return row["prompt_text"] if row else None
