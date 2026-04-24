"""Interaction ingestion pipeline: process_interaction + entity profile sync."""
import json
import logging

from core.storage import get_memory_db_context, flush_interaction_cache, cache_interaction
from memory_services import generate_embedding
from memory_helpers import _get_entity_type_config

logger = logging.getLogger(__name__)


async def process_interaction(interaction_id: str):
    """
    Worker Task: Fetches a pending interaction, extracts attachments, runs vision AI,
    computes ephemeral embeddings, and flags the interaction as processed or failed.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM interactions WHERE id = %s", (interaction_id,))
        row = cursor.fetchone()

    if not row:
        logger.warning(f"process_interaction: Interaction {interaction_id} not found.")
        return

    interaction = dict(row)
    if interaction["status"] not in ["pending", "queued"]:
        logger.info(f"Interaction {interaction_id} is already in status: {interaction['status']}")
        return

    content = interaction.get("content") or ""
    try:
        attachment_refs = json.loads(interaction["attachment_refs"]) if isinstance(interaction.get("attachment_refs"), str) else (interaction.get("attachment_refs") or [])
    except json.JSONDecodeError:
        attachment_refs = []

    processing_errors = {}
    if interaction.get("processing_errors"):
        try:
            processing_errors = json.loads(interaction["processing_errors"]) if isinstance(interaction.get("processing_errors"), str) else interaction["processing_errors"]
        except json.JSONDecodeError:
            pass

    # Document OCR parsing logic
    from memory_services import parse_document
    for attachment in attachment_refs:
        if not isinstance(attachment, dict):
            continue

        attach_type = attachment.get("type", "base64")
        raw_blob = None
        url = attachment.get("url")

        if attach_type == "url":
            if url:
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        raw_blob = resp.content
                except Exception as e:
                    logger.warning(f"Failed to fetch attachment URL {url}: {e}")
        else:
            b64_data = attachment.get("data") or attachment.get("raw_bytes")
            if b64_data:
                import base64
                try:
                    raw_blob = base64.b64decode(b64_data)
                except Exception as e:
                    logger.warning(f"Failed to decode base64 attachment: {e}")

        if not raw_blob:
            continue

        import filetype
        inferred_mime = None
        kind = filetype.guess(raw_blob)
        if kind: inferred_mime = kind.mime

        mime_type = inferred_mime or attachment.get("mime_type", "application/octet-stream")
        filename = attachment.get("filename", "attachment")

        try:
            parsed = await parse_document(raw_blob, filename, mime_type)
        except Exception as e:
            logger.error(f"Vision/Processing failed for {filename}: {e}")
            processing_errors["vision"] = str(e)
            parsed = {}

        url_context = f" ({url})" if attach_type == "url" and url else ""
        pages_context = f" (Parsed {parsed.get('parsed_pages', parsed.get('pages', 1))} out of {parsed.get('pages', 1)} pages)" if mime_type == "application/pdf" and parsed.get("pages", 0) > 0 else ""

        if parsed.get("text"):
            content += f"\n\n---\n[Attachment ({mime_type}): {filename}]{url_context}{pages_context}\n{parsed['text']}"
            attachment["parsed_content"] = parsed["text"]
        else:
            err_msg = processing_errors.get("vision", "Parsing Failed or Document is Empty")
            content += f"\n\n---\n[Attachment ({mime_type}): {filename}]{url_context}{pages_context}\n[Error: {err_msg}]"

        attachment["inferred_mime"] = mime_type

    # Real-time Embeddings generation for Pending Interactions (Ephemeral Vectors)
    embedding = None
    try:
        if content.strip():
            embedding = await generate_embedding(content)
    except Exception as e:
        logger.warning(f"Failed to generate ephemeral interaction embedding: {e}")
        processing_errors["embeddings"] = str(e)
        content += f"\n\n[Processing Error: Embedding Failed - {e}]"

    # Save outputs to Database
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        if embedding:
            cursor.execute("""
                UPDATE interactions
                SET content = %s, attachment_refs = %s, embedding = %s, processing_errors = %s, is_enriched = TRUE
                WHERE id = %s
            """, (
                content, json.dumps(attachment_refs, ensure_ascii=False), embedding,
                json.dumps(processing_errors, ensure_ascii=False), interaction_id
            ))
        else:
            cursor.execute("""
                UPDATE interactions
                SET content = %s, attachment_refs = %s, processing_errors = %s, is_enriched = TRUE
                WHERE id = %s
            """, (
                content, json.dumps(attachment_refs, ensure_ascii=False),
                json.dumps(processing_errors, ensure_ascii=False), interaction_id
            ))

    # Cache invalidation to reflect accurate embedding in ephemeral searches
    try:
        mfm = interaction.get("metadata_field_map")
        mfm_parsed = json.loads(mfm) if isinstance(mfm, str) else (mfm or {})
        flush_interaction_cache(interaction_id)
        cache_interaction(interaction_id, {
            "id": interaction_id,
            "interaction_type": interaction["interaction_type"],
            "agent_id": interaction.get("agent_id"),
            "content": content,
            "primary_entity_type": interaction["primary_entity_type"],
            "primary_entity_id": interaction["primary_entity_id"],
            "timestamp": str(interaction["timestamp"]),
            "metadata_field_map": mfm_parsed,
        })
    except Exception as e:
        logger.warning(f"Cache update failed for interaction {interaction_id}: {e}")

    # Trigger Outbound Webhooks logic
    try:
        from services.outbound_webhooks import evaluate_outbound_webhooks
        await evaluate_outbound_webhooks(interaction_id)
    except Exception as e:
        logger.error(f"Failed to evaluate outbound webhooks for {interaction_id}: {e}")

    # Entity Profile Extraction — sync display_name, subtype, status from CRM blob
    try:
        _sync_entity_profile(interaction)
    except Exception as e:
        logger.warning(f"Entity profile sync failed for {interaction_id}: {e}")


def _sync_entity_profile(interaction: dict):
    """Extract entity profile data from interaction metadata/content using the entity type's field map.

    Reads metadata_field_map from entity type config to know which CRM fields to extract.
    Checks profile_sync_triggers to decide if this interaction type should trigger extraction.
    Falls back to parsing content as JSON if metadata is empty.
    Auto-discovers schema keys from the first interaction for a new entity type.
    """
    entity_type = interaction.get("primary_entity_type", "")
    entity_id = interaction.get("primary_entity_id", "")
    interaction_type = interaction.get("interaction_type", "")
    if not entity_type or not entity_id:
        return

    config = _get_entity_type_config(entity_type)
    field_map = config.get("metadata_field_map") or {}
    if isinstance(field_map, str):
        field_map = json.loads(field_map)

    sync_triggers = field_map.get("profile_sync_triggers", ["initial_memory_context"])
    if interaction_type not in sync_triggers:
        return

    raw_data = interaction.get("metadata") or {}
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            raw_data = {}

    if not raw_data or not isinstance(raw_data, dict):
        content = interaction.get("content", "")
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    raw_data = parsed[0].get("json", parsed[0])
                elif isinstance(parsed, dict):
                    raw_data = parsed
            except (json.JSONDecodeError, TypeError):
                pass

    if not raw_data or not isinstance(raw_data, dict):
        logger.debug(f"No structured data found for profile sync: {entity_type}/{entity_id}")
        return

    display_name = raw_data.get(field_map.get("name_field", ""), None)
    subtype = raw_data.get(field_map.get("subtype_field", ""), None)
    status = raw_data.get(field_map.get("status_field", ""), None)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO entity_profiles (entity_type, entity_id, display_name, subtype, status, properties, first_seen_at, last_synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (entity_type, entity_id) DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, entity_profiles.display_name),
                subtype = COALESCE(EXCLUDED.subtype, entity_profiles.subtype),
                status = COALESCE(EXCLUDED.status, entity_profiles.status),
                properties = EXCLUDED.properties,
                last_synced_at = NOW()
        """, (
            entity_type, entity_id,
            str(display_name) if display_name else None,
            str(subtype) if subtype else None,
            str(status) if status else None,
            json.dumps(raw_data, ensure_ascii=False, default=str),
        ))

        if subtype and not interaction.get("primary_entity_subtype"):
            cursor.execute(
                "UPDATE interactions SET primary_entity_subtype = %s WHERE id = %s AND primary_entity_subtype IS NULL",
                (str(subtype), interaction["id"])
            )

    existing_schema = config.get("discovered_schema")
    if not existing_schema:
        discovered_keys = sorted([k for k in raw_data.keys() if isinstance(k, str)])
        if discovered_keys:
            try:
                with get_memory_db_context() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE memory_entity_type_config SET discovered_schema = %s WHERE entity_type = %s AND discovered_schema IS NULL",
                        (json.dumps(discovered_keys), entity_type)
                    )
                logger.info(f"Auto-discovered {len(discovered_keys)} schema fields for entity type '{entity_type}'")
            except Exception as e:
                logger.warning(f"Failed to save discovered schema for {entity_type}: {e}")

    logger.info(f"Entity profile synced: {entity_type}/{entity_id} → name={display_name}, subtype={subtype}, status={status}")
