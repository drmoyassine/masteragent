"""
routes/prompts.py — Prompt and section CRUD endpoints

Handles: prompt list/create/get/update/delete,
         section list/get/create/update/delete/reorder,
         prompt version list/create.

Shared helpers (slugify, extract_variables) are defined here and re-exported so
routes/render.py can import them without circular dependencies.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import require_auth
from core.db import get_db_context, get_github_settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class PromptCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    template_id: Optional[str] = None


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PromptResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    folder_path: str
    created_at: str
    updated_at: str
    versions: List[Dict[str, Any]] = []


class SectionCreate(BaseModel):
    name: str
    title: str
    content: str
    order: Optional[int] = None
    parent_path: Optional[str] = None


class SectionUpdate(BaseModel):
    content: str


class SectionReorder(BaseModel):
    sections: List[Dict[str, Any]]


class VersionCreate(BaseModel):
    version_name: str
    source_version: Optional[str] = None


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text


def extract_variables(content: str) -> List[str]:
    """Extract {{variable}} names from content."""
    pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}"
    return list(set(re.findall(pattern, content)))


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
                cursor.execute("SELECT name, value FROM account_variables WHERE user_id = ?", (user_id,))
                for row in cursor.fetchall():
                    resolved[row["name"]] = row["value"]
                    
            # 2. Prompt-level variables (medium priority)
            if prompt_id:
                cursor.execute(
                    "SELECT name, value FROM prompt_variables WHERE prompt_id = ? AND version = ?",
                    (prompt_id, version),
                )
                for row in cursor.fetchall():
                    resolved[row["name"]] = row["value"]

    # 1. Runtime values (highest priority)
    resolved.update(variables)
    result = content
    for key, value in resolved.items():
        if value is not None:
            result = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", str(value), result)
    return result


# ─────────────────────────────────────────────
# Prompt Endpoints
# ─────────────────────────────────────────────

@router.get("/prompts")
async def get_prompts(user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE user_id = ? ORDER BY updated_at DESC", (user["id"],))
        prompts = [dict(row) for row in cursor.fetchall()]
        for prompt in prompts:
            cursor.execute("SELECT * FROM prompt_versions WHERE prompt_id = ? ORDER BY created_at", (prompt["id"],))
            prompt["versions"] = [dict(v) for v in cursor.fetchall()]
    return prompts


@router.post("/prompts", response_model=PromptResponse)
async def create_prompt(prompt_data: PromptCreate, user: dict = Depends(require_auth)):
    from storage_service import get_storage_service, get_storage_mode

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM prompts WHERE user_id = ?", (user["id"],))
        count = cursor.fetchone()["count"]
        if user.get("plan") == "free" and count >= 1:
            raise HTTPException(
                status_code=403,
                detail="Free plan limited to 1 prompt. Upgrade to Pro for unlimited prompts.",
            )

    prompt_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    prompt_slug = slugify(prompt_data.name)
    folder_path = f"prompts/{prompt_slug}"

    storage_mode = get_storage_mode(user["id"])
    if storage_mode == "github":
        settings = get_github_settings(user["id"])
        if not settings or not settings.get("github_token"):
            storage_mode = "local"

    sections_to_create = []
    if prompt_data.template_id:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sections FROM templates WHERE id = ?", (prompt_data.template_id,))
            t = cursor.fetchone()
            if t:
                sections_to_create = json.loads(t["sections"])

    sections = [
        {
            "filename": f"{str(s['order']).zfill(2)}_{s['name']}.md",
            "content": s.get("content", ""),
            "order": s.get("order", 1),
            "name": s.get("name", "section"),
        }
        for s in sections_to_create
    ]
    variables = {}
    for s in sections_to_create:
        for v in extract_variables(s.get("content", "")):
            if v not in variables:
                variables[v] = {"required": True}

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO prompts (id, user_id, name, description, folder_path, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (prompt_id, user["id"], prompt_data.name, prompt_data.description or "", folder_path, now, now),
        )
        version_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO prompt_versions (id, prompt_id, version_name, branch_name, is_default, created_at) VALUES (?,?,?,?,1,?)",
            (version_id, prompt_id, "v1", "v1", now),
        )

    try:
        storage_service = get_storage_service(user["id"])
        await storage_service.create_prompt(
            folder_path=folder_path,
            name=prompt_data.name,
            description=prompt_data.description or "",
            sections=sections,
            variables=variables,
        )
    except Exception as e:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM prompt_versions WHERE prompt_id = ?", (prompt_id,))
            cursor.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        raise HTTPException(status_code=500, detail=f"Failed to create prompt: {e}")

    return PromptResponse(
        id=prompt_id,
        name=prompt_data.name,
        description=prompt_data.description,
        folder_path=folder_path,
        created_at=now,
        updated_at=now,
        versions=[{"id": version_id, "version_name": "v1", "branch_name": "v1", "is_default": True}],
    )


@router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: str, user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        prompt = dict(row)
        cursor.execute("SELECT * FROM prompt_versions WHERE prompt_id = ?", (prompt_id,))
        prompt["versions"] = [dict(v) for v in cursor.fetchall()]
    return prompt


@router.put("/prompts/{prompt_id}")
async def update_prompt(prompt_id: str, prompt_data: PromptUpdate, user: dict = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Prompt not found")
        updates, params = [], []
        if prompt_data.name:
            updates.append("name = ?")
            params.append(prompt_data.name)
        if prompt_data.description is not None:
            updates.append("description = ?")
            params.append(prompt_data.description)
        updates.append("updated_at = ?")
        params.extend([now, prompt_id])
        cursor.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE id = ?", params)
    return await get_prompt(prompt_id, user)


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str, user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Prompt not found")
        cursor.execute("DELETE FROM prompt_versions WHERE prompt_id = ?", (prompt_id,))
        cursor.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    return {"message": "Prompt deleted"}


# ─────────────────────────────────────────────
# Section Endpoints
# ─────────────────────────────────────────────

@router.get("/prompts/{prompt_id}/sections")
async def get_prompt_sections(prompt_id: str, version: str = "v1", user: dict = Depends(require_auth)):
    from storage_service import get_storage_service

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]

    try:
        storage_service = get_storage_service(user["id"])
        content = await storage_service.get_prompt_content(folder_path, version)
        if not content:
            return []
        sections = []
        for section in content.get("sections", []):
            filename = section.get("filename", "")
            m = re.match(r"^(\d+)_(.+)\.md$", filename)
            order = int(m.group(1)) if m else 99
            name = m.group(2) if m else filename.replace(".md", "")
            sections.append({
                "filename": filename,
                "name": name,
                "order": order,
                "path": f"{folder_path}/{version}/{filename}",
                "type": "file",
            })
        sections.sort(key=lambda x: x["order"])
        return sections
    except Exception as e:
        logger.error(f"Error fetching sections: {e}")
        return []


@router.get("/prompts/{prompt_id}/sections/{filename}")
async def get_section_content(prompt_id: str, filename: str, version: str = "v1", user: dict = Depends(require_auth)):
    from storage_service import get_storage_service

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]

    try:
        storage_service = get_storage_service(user["id"])
        section_data = await storage_service.get_section(folder_path, filename, version)
        if not section_data:
            raise HTTPException(status_code=404, detail="Section not found")
        content = section_data.get("content", "")
        return {"filename": filename, "content": content, "variables": extract_variables(content)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching section: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch section: {e}")


@router.post("/prompts/{prompt_id}/sections")
async def create_section(
    prompt_id: str,
    section_data: SectionCreate,
    version: str = "v1",
    user: dict = Depends(require_auth),
):
    from storage_service import get_storage_service

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]

    sections = await get_prompt_sections(prompt_id, version, user)
    order = section_data.order if section_data.order else (max((s["order"] for s in sections), default=0) + 1)
    filename = f"{str(order).zfill(2)}_{slugify(section_data.name)}.md"

    try:
        storage_service = get_storage_service(user["id"])
        success = await storage_service.create_section(folder_path, filename, section_data.content, version)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create section")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating section: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create section: {e}")

    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE prompts SET updated_at = ? WHERE id = ?", (now, prompt_id))

    return {"filename": filename, "message": "Section created"}


@router.put("/prompts/{prompt_id}/sections/{filename}")
async def update_section(
    prompt_id: str,
    filename: str,
    section_data: SectionUpdate,
    version: str = "v1",
    user: dict = Depends(require_auth),
):
    from storage_service import get_storage_service

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]

    try:
        storage_service = get_storage_service(user["id"])
        success = await storage_service.update_section(folder_path, filename, section_data.content, version)
        if not success:
            raise HTTPException(status_code=404, detail="Section not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating section: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update section: {e}")

    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE prompts SET updated_at = ? WHERE id = ?", (now, prompt_id))
    return {"filename": filename, "message": "Section updated"}


@router.delete("/prompts/{prompt_id}/sections/{filename}")
async def delete_section(
    prompt_id: str, filename: str, version: str = "v1", user: dict = Depends(require_auth)
):
    from storage_service import get_storage_service

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]

    try:
        storage_service = get_storage_service(user["id"])
        success = await storage_service.delete_section(folder_path, filename, version)
        if not success:
            raise HTTPException(status_code=404, detail="Section not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting section: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete section: {e}")
    return {"message": "Section deleted"}


@router.post("/prompts/{prompt_id}/sections/reorder")
async def reorder_sections(
    prompt_id: str,
    reorder_data: SectionReorder,
    version: str = "v1",
    user: dict = Depends(require_auth),
):
    from storage_service import get_storage_service

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]

    try:
        storage_service = get_storage_service(user["id"])
        for i, section in enumerate(reorder_data.sections):
            old_filename = section["filename"]
            name = section.get("name", old_filename.split("_", 1)[1].replace(".md", ""))
            new_filename = f"{str(i + 1).zfill(2)}_{name}.md"
            if old_filename != new_filename:
                section_data = await storage_service.get_section(folder_path, old_filename, version)
                if section_data:
                    await storage_service.create_section(folder_path, new_filename, section_data["content"], version)
                    await storage_service.delete_section(folder_path, old_filename, version)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reordering sections: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reorder sections: {e}")
    return {"message": "Sections reordered"}


# ─────────────────────────────────────────────
# Version Endpoints
# ─────────────────────────────────────────────

@router.get("/prompts/{prompt_id}/versions")
async def get_prompt_versions(prompt_id: str):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompt_versions WHERE prompt_id = ? ORDER BY created_at DESC", (prompt_id,))
        return [dict(row) for row in cursor.fetchall()]


@router.post("/prompts/{prompt_id}/versions")
async def create_version(prompt_id: str, version_data: VersionCreate):
    import uuid
    from routes.render import github_api_request

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Prompt not found")

    branch_name = slugify(version_data.version_name)
    source_branch = version_data.source_version or "main"

    ref_data = await github_api_request("GET", f"/git/refs/heads/{source_branch}")
    if not ref_data:
        raise HTTPException(status_code=400, detail=f"Source branch '{source_branch}' not found")

    await github_api_request("POST", "/git/refs", {
        "ref": f"refs/heads/{branch_name}",
        "sha": ref_data["object"]["sha"],
    })

    version_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO prompt_versions (id, prompt_id, version_name, branch_name, is_default, created_at) VALUES (?,?,?,?,0,?)",
            (version_id, prompt_id, version_data.version_name, branch_name, now),
        )
    return {"id": version_id, "version_name": version_data.version_name, "branch_name": branch_name}
