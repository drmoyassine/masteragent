"""
routes/api_keys.py — API key management endpoints
"""
import secrets
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.db import get_db_context

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    name: str


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_preview: str
    created_at: str
    last_used: Optional[str] = None


class APIKeyCreateResponse(APIKeyResponse):
    key: str  # Full key shown only on creation


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.get("/keys", response_model=List[APIKeyResponse])
async def get_api_keys():
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, key_preview, created_at, last_used FROM api_keys ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


@router.post("/keys", response_model=APIKeyCreateResponse)
async def create_api_key(key_data: APIKeyCreate):
    key_id = str(uuid.uuid4())
    full_key = f"pm_{secrets.token_urlsafe(32)}"
    key_preview = f"{full_key[:7]}...{full_key[-4:]}"
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO api_keys (id, name, key_hash, key_preview, created_at) VALUES (?,?,?,?,?)",
            (key_id, key_data.name, full_key, key_preview, now),
        )
    return APIKeyCreateResponse(
        id=key_id, name=key_data.name, key=full_key, key_preview=key_preview, created_at=now
    )


@router.delete("/keys/{key_id}")
async def delete_api_key(key_id: str):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    return {"message": "API key deleted"}
