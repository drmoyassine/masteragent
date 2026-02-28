"""
routes/settings.py — Settings endpoints

Handles: GitHub settings CRUD, storage mode switching, GitHub user lookup.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import require_auth
from core.db import get_db_context, get_github_settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class SettingsCreate(BaseModel):
    github_token: str
    github_repo: str
    github_owner: str
    create_repo: bool = False


class SettingsResponse(BaseModel):
    id: int
    github_repo: Optional[str] = None
    github_owner: Optional[str] = None
    is_configured: bool = False
    has_github: bool = False
    storage_mode: str = "github"


class StorageModeUpdate(BaseModel):
    storage_mode: str  # 'github' or 'local'


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_settings(user: dict = Depends(require_auth)):
    settings = get_github_settings(user["id"])
    if settings:
        storage_mode = settings.get("storage_mode", "local")
        has_github = bool(settings.get("github_token")) and bool(settings.get("github_repo"))
        is_configured = True if storage_mode == "local" else has_github
        return SettingsResponse(
            id=settings["id"],
            github_repo=settings.get("github_repo"),
            github_owner=settings.get("github_owner"),
            is_configured=is_configured,
            has_github=has_github,
            storage_mode=storage_mode,
        )
    return SettingsResponse(id=0, is_configured=True, has_github=False, storage_mode="local")


@router.post("/settings", response_model=SettingsResponse)
async def save_settings(settings_data: SettingsCreate, user: dict = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    headers = {
        "Authorization": f"Bearer {settings_data.github_token}", # Switched to Bearer
        "Accept": "application/vnd.github.v3+json",
    }
    async with httpx.AsyncClient() as client:
        if settings_data.create_repo:
            create_resp = await client.post(
                "https://api.github.com/user/repos",
                headers=headers,
                json={
                    "name": settings_data.github_repo,
                    "description": "Prompt Manager - AI prompt versioning repository",
                    "private": False,
                    "auto_init": True,
                },
            )
            if create_resp.status_code == 201:
                settings_data.github_owner = create_resp.json()["owner"]["login"]
            elif create_resp.status_code != 422:
                raise HTTPException(status_code=400, detail=f"Failed to create repository: {create_resp.text}")

        resp = await client.get(
            f"https://api.github.com/repos/{settings_data.github_owner}/{settings_data.github_repo}",
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error(f"GitHub repository check failed for {settings_data.github_owner}/{settings_data.github_repo}. Status: {resp.status_code}, Body: {resp.text}")
            raise HTTPException(status_code=400, detail=f"Invalid GitHub credentials or repository not found: {resp.text}")

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM settings WHERE user_id = ?", (user["id"],))
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                "UPDATE settings SET github_token=?, github_repo=?, github_owner=?, storage_mode='github', updated_at=? WHERE user_id=?",
                (settings_data.github_token, settings_data.github_repo, settings_data.github_owner, now, user["id"]),
            )
            settings_id = existing["id"]
        else:
            cursor.execute(
                "INSERT INTO settings (user_id, github_token, github_repo, github_owner, storage_mode, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (user["id"], settings_data.github_token, settings_data.github_repo, settings_data.github_owner, 'github', now, now),
            )
            settings_id = cursor.lastrowid

    return SettingsResponse(
        id=settings_id,
        github_repo=settings_data.github_repo,
        github_owner=settings_data.github_owner,
        is_configured=True,
        has_github=True,
        storage_mode="github",
    )


@router.delete("/settings")
async def delete_settings(user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM settings WHERE user_id = ?", (user["id"],))
    return {"message": "Settings deleted"}


@router.post("/settings/storage-mode", response_model=SettingsResponse)
async def set_storage_mode(mode_data: StorageModeUpdate, user: dict = Depends(require_auth)):
    """Set the storage mode for the user (github or local)."""
    if mode_data.storage_mode not in ["github", "local"]:
        raise HTTPException(status_code=400, detail="Invalid storage mode. Must be 'github' or 'local'")
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user["id"],))
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                "UPDATE settings SET storage_mode=?, updated_at=? WHERE user_id=?",
                (mode_data.storage_mode, now, user["id"]),
            )
            settings_id = existing["id"]
            is_configured = True if mode_data.storage_mode == "local" else bool(existing.get("github_token"))
            has_github = bool(existing.get("github_token"))
            github_repo = existing.get("github_repo")
            github_owner = existing.get("github_owner")
        else:
            cursor.execute(
                "INSERT INTO settings (user_id, storage_mode, created_at, updated_at) VALUES (?,?,?,?)",
                (user["id"], mode_data.storage_mode, now, now),
            )
            settings_id = cursor.lastrowid
            is_configured = mode_data.storage_mode == "local"
            has_github = False
            github_repo = None
            github_owner = None

    return SettingsResponse(
        id=settings_id,
        github_repo=github_repo,
        github_owner=github_owner,
        is_configured=is_configured,
        has_github=has_github,
        storage_mode=mode_data.storage_mode,
    )


@router.get("/github/user")
async def get_github_user(token: str):
    """Get GitHub user info from token."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://api.github.com/user", headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid GitHub token")
        return resp.json()
