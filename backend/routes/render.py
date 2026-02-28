"""
routes/render.py — Prompt rendering endpoint

Handles: POST /prompts/{prompt_id}/{version}/render
         (authenticated by API key — open access for external agents)

Also exposes github_api_request() used by routes/prompts.py create_version.
"""
import base64
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import verify_api_key
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
):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        prompt = cursor.fetchone()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = prompt["folder_path"]
        user_id = prompt["user_id"]

    # Get sections via storage_service (delegated to prompts router helper)
    from routes.prompts import get_prompt_sections

    # Use a minimal user dict to satisfy require_auth
    fake_user = {"id": user_id}
    sections = await get_prompt_sections(prompt_id, version, fake_user)
    if not sections:
        raise HTTPException(status_code=404, detail="No sections found")

    compiled_parts = []
    sections_used = []
    all_variables = set()

    for section in sections:
        file_data = await github_api_request("GET", f"/contents/{folder_path}/{section['filename']}?ref={version}")
        if file_data:
            content = base64.b64decode(file_data["content"]).decode("utf-8")
            all_variables.update(extract_variables(content))
            content = inject_variables(
                content,
                render_data.variables or {},
                prompt_id=prompt_id,
                user_id=user_id,
                version=version,
            )
            compiled_parts.append(content)
            sections_used.append(section["filename"])

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
