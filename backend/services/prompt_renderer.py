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
    """Inject variables with resolution order: account → prompt → entity profile → runtime."""
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

    # ── Entity profile resolution ──
    # If entity_type + entity_id are in the runtime variables, resolve entity
    # profile properties as dot-notation variables (e.g., entity.name, contact.status)
    entity_type = resolved.get("entity_type") or resolved.get("entity.type")
    entity_id = resolved.get("entity_id") or resolved.get("entity.id")

    if entity_type and entity_id:
        try:
            entity_vars = _resolve_entity_profile_variables(entity_type, entity_id)
            # Entity vars have lower priority than explicit runtime values
            for k, v in entity_vars.items():
                if k not in resolved:
                    resolved[k] = v
        except Exception as e:
            logger.debug(f"Entity profile resolution skipped: {e}")
    
    # Flatten variables to support dot notation (e.g., {{entity.name}})
    flat_resolved = _flatten_dict(resolved)
    
    result = content
    for key, value in flat_resolved.items():
        if value is not None:
            # Need to replace {{ key }} handling spaces inside braces
            result = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", str(value), result)
            
    return result


def _resolve_entity_profile_variables(entity_type: str, entity_id: str) -> dict:
    """Resolve entity profile data into dot-notation variables.
    
    Reads entity_profiles + memory_entity_type_config to build:
      - entity.type, entity.id, entity.name, entity.status, etc.
      - {entity_type}.name, {entity_type}.status, etc. (e.g., contact.name)
    """
    from core.storage import get_memory_db_context

    entity_vars = {}

    # Always set the basic entity identifiers
    entity_vars["entity"] = {"type": entity_type, "id": entity_id}
    entity_vars[entity_type] = {"type": entity_type, "id": entity_id}

    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()

            # Fetch entity profile
            cursor.execute(
                "SELECT display_name, subtype, status, properties FROM entity_profiles WHERE entity_type = %s AND entity_id = %s",
                (entity_type, entity_id),
            )
            profile = cursor.fetchone()

            # Fetch entity type config for field mappings
            cursor.execute(
                "SELECT metadata_field_map, discovered_schema FROM memory_entity_type_config WHERE entity_type = %s",
                (entity_type,),
            )
            config = cursor.fetchone()

        if profile:
            # Map the semantic role fields
            entity_vars["entity"]["name"] = profile.get("display_name") or entity_id
            entity_vars["entity"]["subtype"] = profile.get("subtype") or ""
            entity_vars["entity"]["status"] = profile.get("status") or ""
            entity_vars[entity_type]["name"] = profile.get("display_name") or entity_id
            entity_vars[entity_type]["subtype"] = profile.get("subtype") or ""
            entity_vars[entity_type]["status"] = profile.get("status") or ""

            # Also expose all properties from the profile
            properties = profile.get("properties") or {}
            if isinstance(properties, str):
                import json as _json
                properties = _json.loads(properties)

            for prop_key, prop_value in properties.items():
                entity_vars["entity"][prop_key] = prop_value
                entity_vars[entity_type][prop_key] = prop_value

        if config:
            field_map = config.get("metadata_field_map") or {}
            if isinstance(field_map, str):
                import json as _json
                field_map = _json.loads(field_map)

            # Map semantic roles to their configured field names for reference
            for role in ("name_field", "subtype_field", "status_field", "summary_field"):
                mapped_field = field_map.get(role)
                if mapped_field and profile:
                    props = profile.get("properties") or {}
                    if isinstance(props, str):
                        import json as _json
                        props = _json.loads(props)
                    role_key = role.replace("_field", "")
                    val = props.get(mapped_field, "")
                    entity_vars["entity"][role_key] = val or entity_vars["entity"].get(role_key, "")
                    entity_vars[entity_type][role_key] = val or entity_vars[entity_type].get(role_key, "")

    except Exception as e:
        logger.debug(f"Failed to resolve entity profile for {entity_type}/{entity_id}: {e}")

    return entity_vars
