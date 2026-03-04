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
    Get active LLM configuration for a task type.
    Includes fallback logic to share API keys across task types for the same provider.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM memory_llm_configs
            WHERE task_type = %s AND is_active = TRUE
            ORDER BY updated_at DESC LIMIT 1
        """, (task_type,))
        row = cursor.fetchone()
        if not row:
            return None

        config = dict(row)
        extra = config.get("extra_settings") or {}
        config["extra_config"] = extra if isinstance(extra, dict) else json.loads(extra)

        # Key Fallback: share keys across task types for the same provider
        if not config.get("api_key_encrypted"):
            provider = config.get("provider")
            if provider not in ["gliner", "zendata", "custom"]:
                cursor.execute("""
                    SELECT api_key_encrypted, api_base_url
                    FROM memory_llm_configs
                    WHERE provider = %s AND api_key_encrypted IS NOT NULL AND api_key_encrypted != ''
                    ORDER BY updated_at DESC LIMIT 1
                """, (provider,))
                fallback = cursor.fetchone()
                if fallback:
                    config["api_key_encrypted"] = fallback["api_key_encrypted"]
                    if not config.get("api_base_url") and fallback["api_base_url"]:
                        config["api_base_url"] = fallback["api_base_url"]
                    logger.info(f"Using inherited API key for {task_type} from provider {provider}")

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
