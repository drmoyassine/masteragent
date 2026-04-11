import logging
import re
from typing import Any, Dict, List

from core.db import get_db_context

logger = logging.getLogger(__name__)

def extract_variables(content: str) -> List[str]:
    """Extract {{variable}} names from content."""
    pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}"
    return list(set(re.findall(pattern, content)))


def _flatten_dict(d: dict, parent_key: str = '', sep: str = '.') -> dict:
    """Flatten a nested dictionary for dot-notation variable access.
    e.g., {'entity': {'name': 'John'}} -> {'entity.name': 'John'}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def inject_variables(
    content: str,
    variables: dict,
    prompt_id: str = None,
    user_id: str = None,
    version: str = "v1",
) -> str:
    """Inject variables with resolution order: account → prompt → runtime."""
    resolved = {}

    # Bundle DB operations within a single connection
    if user_id or prompt_id:
        with get_db_context() as conn:
            cursor = conn.cursor()

            # 3. Account-level variables (lowest priority)
            if user_id:
                cursor.execute("SELECT name, value FROM account_variables WHERE user_id = %s", (user_id,))
                for row in cursor.fetchall():
                    resolved[row["name"]] = row["value"]

            # 2. Prompt-level variables (medium priority)
            if prompt_id:
                cursor.execute(
                    "SELECT name, value FROM prompt_variables WHERE prompt_id = %s AND version = %s",
                    (prompt_id, version),
                )
                for row in cursor.fetchall():
                    resolved[row["name"]] = row["value"]

    # 1. Runtime values (highest priority)
    resolved.update(variables)
    
    # Flatten variables to support dot notation (e.g., {{entity.name}})
    flat_resolved = _flatten_dict(resolved)
    
    result = content
    for key, value in flat_resolved.items():
        if value is not None:
            # Need to replace {{ key }} handling spaces inside braces
            result = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", str(value), result)
            
    return result
