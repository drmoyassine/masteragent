"""
routes/render.py — Prompt rendering endpoint

Handles: POST /prompts/{prompt_id}/{version}/render
         (authenticated by API key — open access for external agents)

Also exposes github_api_request() used by routes/prompts.py create_version.
"""
import base64
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from core.auth import verify_api_key, get_current_user
from core.db import get_db_context, get_github_settings
from routes.prompts import extract_variables, inject_variables

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class RenderRequest(BaseModel):
    variables: Optional[Dict[str, Any]] = {}


class RenderResponse(BaseModel):
    prompt_id: str
    version: str
    compiled_prompt: str
    sections_used: List[str]


# ─────────────────────────────────────────────
# GitHub API Helper (also used by prompts.create_version)
# ─────────────────────────────────────────────

async def github_api_request(method: str, endpoint: str, data: dict = None, user_id: str = None):
    settings = get_github_settings(user_id)
    if not settings or not settings.get("github_token"):
        raise HTTPException(status_code=400, detail="GitHub not configured")
    headers = {
        "Authorization": f"token {settings['github_token']}",
        "Accept": "application/vnd.github.v3+json",
    }
    base_url = f"https://api.github.com/repos/{settings['github_owner']}/{settings['github_repo']}"
    url = f"{base_url}{endpoint}"
    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "PUT":
            response = await client.put(url, headers=headers, json=data)
        elif method == "POST":
            response = await client.post(url, headers=headers, json=data)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        if response.status_code == 204:
            return {}
        return response.json()


# ─────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────

@router.post("/prompts/{prompt_id}/{version}/render", response_model=RenderResponse)
async def render_prompt(
    prompt_id: str,
    version: str,
    render_data: RenderRequest,
    api_key: dict = Depends(verify_api_key),
    authorization: str = Header(None),
):
    if not api_key and not authorization:
        raise HTTPException(status_code=401, detail="Prompt credentials required")
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = %s", (prompt_id,))
        prompt = cursor.fetchone()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = prompt["folder_path"]
        user_id = prompt["user_id"]

    # Browser preview uses the owner's JWT; external consumers use a prompt API
    # key. Legacy keys created before ownership was introduced have user_id NULL
    # and retain their historical global behavior during the migration window.
    jwt_user = get_current_user(authorization) if authorization else None
    legacy_global_keys = os.environ.get("LEGACY_PROMPT_KEYS_GLOBAL", "true").lower() in {"1", "true", "yes"}
    key_allowed = bool(
        api_key and (
            api_key.get("is_service")
            or (api_key.get("user_id") is None and legacy_global_keys)
            or api_key.get("user_id") == user_id
        )
    )
    user_allowed = bool(jwt_user and (jwt_user.get("id") == user_id or jwt_user.get("is_admin")))
    if not key_allowed and not user_allowed:
        raise HTTPException(status_code=401 if not api_key and not jwt_user else 403, detail="Prompt access denied")

    # Get sections via storage service (works for both local and GitHub storage)
    from storage_service import get_storage_service

    storage_service = get_storage_service(user_id)
    prompt_content = await storage_service.get_prompt_content(folder_path, version)
    if not prompt_content or not prompt_content.get("sections"):
        raise HTTPException(status_code=404, detail="No sections found")

    compiled_parts = []
    sections_used = []
    all_variables = set()

    for section in prompt_content["sections"]:
        content = section.get("content", "")
        filename = section.get("filename", "unknown")
        all_variables.update(extract_variables(content))
        content = inject_variables(
            content,
            render_data.variables or {},
            prompt_id=prompt_id,
            user_id=user_id,
            version=version,
        )
        compiled_parts.append(content)
        sections_used.append(filename)

    compiled_prompt = "\n\n---\n\n".join(compiled_parts)
    remaining = extract_variables(compiled_prompt)
    if remaining:
        raise HTTPException(
            status_code=400,
            detail={"error": "Missing required variables", "missing": remaining},
        )

    return RenderResponse(
        prompt_id=prompt_id,
        version=version,
        compiled_prompt=compiled_prompt,
        sections_used=sections_used,
    )
