"""
memory/webhooks.py — Inbound webhook ingestion + source management

Endpoints:
  POST   /webhooks           — register a webhook source (admin JWT)
  GET    /webhooks           — list registered sources    (admin JWT)
  PATCH  /webhooks/{id}      — update a source            (admin JWT)
  DELETE /webhooks/{id}      — remove a source            (admin JWT)
  POST   /webhooks/inbound/{source_id}  — receive event   (HMAC-SHA256 verified)

Inbound flow:
  1. Verify X-Webhook-Signature header (HMAC-SHA256 of raw body with source secret)
  2. Normalize payload using source's metadata_field_map
  3. Map event type → interaction_type
  4. Insert interaction record (same as /api/memory/interactions)
  5. Cache in Redis (24h TTL)
"""
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query
from pydantic import BaseModel

from core.storage import get_memory_db_context, cache_interaction
from memory.auth import require_admin_auth

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────

class WebhookSourceCreate(BaseModel):
    name: str
    source_system: str                      # e.g. hubspot, pipedrive, n8n, make, custom
    event_types: Optional[List[str]] = []   # whitelist; empty = accept all
    metadata_field_map: Optional[dict] = {} # {"content_field": "body", "entity_id_field": "contactId", ...}
    default_interaction_type: str = "webhook_event"
    default_entity_type: str = "contact"
    is_active: bool = True

class WebhookSourceUpdate(BaseModel):
    name: Optional[str] = None
    event_types: Optional[List[str]] = None
    metadata_field_map: Optional[dict] = None
    default_interaction_type: Optional[str] = None
    default_entity_type: Optional[str] = None
    is_active: Optional[bool] = None

class WebhookSourceResponse(BaseModel):
    id: str
    name: str
    source_system: str
    event_types: List[str]
    metadata_field_map: dict
    default_interaction_type: str
    default_entity_type: str
    is_active: bool
    created_at: str


# ─────────────────────────────────────────────────────────────
# Source Management (admin-protected)
# ─────────────────────────────────────────────────────────────

@router.post("/webhooks")
async def register_webhook_source(
    body: WebhookSourceCreate,
    admin: dict = Depends(require_admin_auth)
):
    """Register a new webhook source. Returns the signing secret (shown once)."""
    source_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)          # plain text — shown once
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_webhook_sources (
                id, name, source_system, secret_hash,
                event_types, metadata_field_map,
                default_interaction_type, default_entity_type,
                is_active, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            source_id, body.name, body.source_system, secret_hash,
            body.event_types or [],
            json.dumps(body.metadata_field_map or {}),
            body.default_interaction_type,
            body.default_entity_type,
            body.is_active,
            now,
        ))

    inbound_url = f"/api/memory/webhooks/inbound/{source_id}"
    return {
        "id": source_id,
        "signing_secret": secret,   # ← shown once, cannot be retrieved later
        "inbound_url": inbound_url,
        "created_at": now,
        "note": "Store the signing_secret securely. It will not be shown again.",
    }


@router.get("/webhooks")
async def list_webhook_sources(
    active_only: bool = Query(True),
    admin: dict = Depends(require_admin_auth)
):
    """List registered webhook sources."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        where = "WHERE is_active = TRUE" if active_only else ""
        cursor.execute(f"""
            SELECT id, name, source_system, event_types, metadata_field_map,
                   default_interaction_type, default_entity_type, is_active, created_at
            FROM memory_webhook_sources {where}
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()

    sources = []
    for row in rows:
        s = dict(row)
        if isinstance(s.get("metadata_field_map"), str):
            s["metadata_field_map"] = json.loads(s["metadata_field_map"])
        if isinstance(s.get("event_types"), str):
            s["event_types"] = json.loads(s["event_types"])
        sources.append(s)

    return {"sources": sources, "total": len(sources)}


@router.patch("/webhooks/{source_id}")
async def update_webhook_source(
    source_id: str,
    body: WebhookSourceUpdate,
    admin: dict = Depends(require_admin_auth)
):
    """Update a webhook source's configuration."""
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []

    if body.name is not None:
        fields.append("name = %s"); values.append(body.name)
    if body.event_types is not None:
        fields.append("event_types = %s"); values.append(body.event_types)
    if body.metadata_field_map is not None:
        fields.append("metadata_field_map = %s"); values.append(json.dumps(body.metadata_field_map))
    if body.default_interaction_type is not None:
        fields.append("default_interaction_type = %s"); values.append(body.default_interaction_type)
    if body.default_entity_type is not None:
        fields.append("default_entity_type = %s"); values.append(body.default_entity_type)
    if body.is_active is not None:
        fields.append("is_active = %s"); values.append(body.is_active)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(source_id)
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE memory_webhook_sources SET {', '.join(fields)} WHERE id = %s",
            values
        )

    return {"id": source_id, "updated": True}


@router.delete("/webhooks/{source_id}", status_code=204)
async def delete_webhook_source(source_id: str, admin: dict = Depends(require_admin_auth)):
    """Remove a webhook source."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_webhook_sources WHERE id = %s", (source_id,))


@router.post("/webhooks/{source_id}/rotate-secret")
async def rotate_webhook_secret(source_id: str, admin: dict = Depends(require_admin_auth)):
    """Generate a new signing secret for an existing webhook source."""
    secret = secrets.token_urlsafe(32)
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE memory_webhook_sources SET secret_hash = %s WHERE id = %s",
            (secret_hash, source_id)
        )

    return {
        "id": source_id,
        "signing_secret": secret,
        "note": "Store the new signing_secret securely. It will not be shown again.",
    }


# ─────────────────────────────────────────────────────────────
# Inbound Webhook Receiver (unauthenticated — HMAC-verified)
# ─────────────────────────────────────────────────────────────

@router.post("/webhooks/inbound/{source_id}")
async def receive_webhook(
    source_id: str,
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
):
    """
    Receive an inbound webhook event from an external system.

    Authentication: HMAC-SHA256 signature in X-Webhook-Signature header.
    Format: sha256=<hex-digest>

    Payload fields resolved via source's metadata_field_map:
      content_field        → interaction content (fallback: stringify whole payload)
      entity_id_field      → primary_entity_id
      entity_type_field    → primary_entity_type (fallback: source.default_entity_type)
      event_type_field     → interaction_type   (fallback: source.default_interaction_type)
    """
    # 1. Load source
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, source_system, secret_hash, event_types,
                   metadata_field_map, default_interaction_type, default_entity_type, is_active
            FROM memory_webhook_sources WHERE id = %s
        """, (source_id,))
        source = cursor.fetchone()

    if not source:
        raise HTTPException(status_code=404, detail="Webhook source not found")
    if not source["is_active"]:
        raise HTTPException(status_code=403, detail="Webhook source is disabled")

    # 2. Read raw body (must do before JSON parse)
    raw_body = await request.body()

    # 3. Verify HMAC signature
    secret_hash = source["secret_hash"]
    if not _verify_signature(raw_body, x_webhook_signature, secret_hash):
        logger.warning(f"Webhook signature verification failed for source {source_id}")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 4. Parse payload
    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 5. Load field map
    field_map = source["metadata_field_map"] or {}
    if isinstance(field_map, str):
        field_map = json.loads(field_map)

    event_types_whitelist = source["event_types"] or []
    if isinstance(event_types_whitelist, str):
        event_types_whitelist = json.loads(event_types_whitelist)

    # 6. Normalize payload using field map
    interaction_type = _extract_field(payload, field_map.get("event_type_field"), source["default_interaction_type"])
    entity_id = _extract_field(payload, field_map.get("entity_id_field"), None)
    entity_type = _extract_field(payload, field_map.get("entity_type_field"), source["default_entity_type"])
    content = _extract_field(payload, field_map.get("content_field"), None)

    # Fallback: stringify the whole payload as content
    if not content:
        content = json.dumps(payload, ensure_ascii=False)

    if not entity_id:
        raise HTTPException(
            status_code=422,
            detail=f"Could not resolve entity_id from payload. Set 'entity_id_field' in metadata_field_map."
        )

    # 7. Event type whitelist check
    if event_types_whitelist and interaction_type not in event_types_whitelist:
        return {"status": "ignored", "reason": f"event_type '{interaction_type}' not in whitelist"}

    # 8. Create interaction record
    now = datetime.now(timezone.utc).isoformat()
    interaction_id = str(uuid.uuid4())

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO interactions (
                id, timestamp, interaction_type, agent_id, agent_name,
                content, primary_entity_type, primary_entity_subtype, primary_entity_id,
                metadata, metadata_field_map, has_attachments, attachment_refs,
                source, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            interaction_id, now, interaction_type,
            None,                               # no agent_id for webhooks
            source["name"],                     # source name as agent_name
            content,
            entity_type, None, entity_id,
            json.dumps(payload),                # store full payload as metadata
            json.dumps(field_map),
            False, json.dumps([]),
            f"webhook:{source['source_system']}",
            "pending",
            now,
        ))

    # 9. Cache in Redis
    cache_interaction(interaction_id, {
        "id": interaction_id,
        "interaction_type": interaction_type,
        "content": content,
        "primary_entity_type": entity_type,
        "primary_entity_id": entity_id,
        "timestamp": now,
        "metadata_field_map": field_map,
        "source": f"webhook:{source['source_system']}",
    })

    logger.info(f"Webhook received: {source_id}/{interaction_type} → interaction {interaction_id}")
    return {"status": "accepted", "interaction_id": interaction_id, "timestamp": now}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _verify_signature(raw_body: bytes, signature_header: Optional[str], stored_secret_hash: str) -> bool:
    """
    Verify X-Webhook-Signature: sha256=<hex>

    Since we only store the HASH of the secret (not the secret itself), we compute
    HMAC-SHA256(key=secret_hash_bytes, msg=raw_body) and compare to the provided
    signature.

    Callers should sign their payloads using:
        hmac.new(signing_secret_hash.encode(), raw_body, hashlib.sha256).hexdigest()

    This is a deliberate trade-off: avoids storing plaintext secrets while keeping
    HMAC-based verification. For higher compatibility with third-party platforms
    (GitHub, Stripe), a future enhancement can store the plaintext secret in an
    encrypted column.
    """
    if not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    provided_sig = signature_header[len("sha256="):]

    expected_sig = hmac.new(
        stored_secret_hash.encode(),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(provided_sig, expected_sig)



def _extract_field(payload: dict, field_path: Optional[str], default=None):
    """
    Extract a value from a nested dict using dot-notation path.
    e.g. field_path="contact.id" → payload["contact"]["id"]
    """
    if not field_path:
        return default
    try:
        keys = field_path.split(".")
        val = payload
        for k in keys:
            val = val[k]
        return str(val) if val is not None else default
    except (KeyError, TypeError):
        return default
