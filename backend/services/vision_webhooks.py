"""Vision/Doc parsing completion webhooks.

Fired once per successfully-parsed attachment with the entity reference, the
source document URL/filename, and the extracted text. Best-effort fire-once
delivery — failures are logged and discarded (vision results are time-sensitive
and there's no value in infinite retry storms for a single parse).
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)

POST_TIMEOUT_SECONDS = 15.0


def _load_active_webhooks() -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, url, doc_type_filter, source_filter
            FROM vision_completion_webhooks
            WHERE is_active = TRUE
        """)
        rows = cursor.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for fld in ("doc_type_filter", "source_filter"):
            v = d.get(fld)
            if isinstance(v, str):
                try:
                    d[fld] = json.loads(v)
                except Exception:
                    d[fld] = None
        out.append(d)
    return out


def _matches_filter(value: Optional[str], allowlist: Optional[List[str]]) -> bool:
    if not allowlist:
        return True  # empty filter = allow all
    if value is None:
        return False
    return value in allowlist


async def fire_vision_completion_webhooks(
    *,
    entity_type: str,
    entity_id: str,
    interaction_id: str,
    doc_url: Optional[str],
    filename: Optional[str],
    mime_type: Optional[str],
    parsed_text: str,
    source: Optional[str] = None,
    parsed_at: Optional[str] = None,
) -> None:
    """Fire all matching active vision completion webhooks. Best-effort, no retry.

    `mime_type` is matched against each webhook's `doc_type_filter` (e.g.
    ["application/pdf", "image/png"]).
    `source` is matched against `source_filter` (the interaction's `source`
    field, e.g. ["chatwoot", "crm"]).
    """
    try:
        hooks = _load_active_webhooks()
    except Exception as e:
        logger.error(f"vision_webhooks: failed to load configs: {e}")
        return

    if not hooks:
        return

    payload = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "interaction_id": interaction_id,
        "doc_url": doc_url,
        "filename": filename,
        "mime_type": mime_type,
        "source": source,
        "parsed_text": parsed_text,
        "parsed_at": parsed_at,
    }

    async with httpx.AsyncClient(timeout=POST_TIMEOUT_SECONDS) as client:
        for h in hooks:
            if not _matches_filter(mime_type, h.get("doc_type_filter")):
                continue
            if not _matches_filter(source, h.get("source_filter")):
                continue
            url = h.get("url")
            name = h.get("name") or h.get("id")
            if not url:
                continue
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code >= 400:
                    logger.warning(
                        f"vision_webhook '{name}' returned {resp.status_code}: {resp.text[:300]}"
                    )
                else:
                    logger.info(
                        f"vision_webhook '{name}' delivered for {entity_type}/{entity_id} "
                        f"(interaction={interaction_id}, mime={mime_type})"
                    )
            except Exception as e:
                logger.error(
                    f"vision_webhook '{name}' delivery failed for {entity_type}/{entity_id}: {e}"
                )
