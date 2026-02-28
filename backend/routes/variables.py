"""
routes/variables.py — Account and prompt variable endpoints

Handles:
  - Account variables: GET/POST/PUT/DELETE /account-variables/*
  - Prompt variables:  GET/POST/PUT/DELETE /prompts/{id}/variables/*
  - Available variables (combined, for autocomplete): GET /prompts/{id}/available-variables
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import require_auth
from core.db import get_db_context

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class VariableBase(BaseModel):
    name: str
    value: Optional[str] = None
    description: Optional[str] = None


class VariableCreate(VariableBase):
    pass


class VariableUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None


class VariableResponse(VariableBase):
    id: str
    created_at: str
    updated_at: str


class PromptVariableResponse(VariableResponse):
    prompt_id: str
    version: str
    required: bool


class AccountVariableResponse(VariableResponse):
    user_id: str


class AvailableVariableResponse(BaseModel):
    name: str
    value: Optional[str] = None
    description: Optional[str] = None
    source: str  # 'account', 'prompt', or 'runtime'
    required: bool = False


# ─────────────────────────────────────────────
# Account Variables
# ─────────────────────────────────────────────

@router.get("/account-variables", response_model=List[AccountVariableResponse])
async def list_account_variables(user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM account_variables WHERE user_id = ? ORDER BY name", (user["id"],))
        return [
            AccountVariableResponse(
                id=row["id"], user_id=row["user_id"], name=row["name"],
                value=row["value"], description=row["description"],
                created_at=row["created_at"], updated_at=row["updated_at"],
            )
            for row in cursor.fetchall()
        ]


@router.post("/account-variables", response_model=AccountVariableResponse)
async def create_account_variable(data: VariableCreate, user: dict = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    var_id = str(uuid.uuid4())
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM account_variables WHERE user_id = ? AND name = ?", (user["id"], data.name))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"Variable '{data.name}' already exists")
        cursor.execute(
            "INSERT INTO account_variables (id, user_id, name, value, description, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (var_id, user["id"], data.name, data.value, data.description, now, now),
        )
    return AccountVariableResponse(
        id=var_id, user_id=user["id"], name=data.name, value=data.value,
        description=data.description, created_at=now, updated_at=now,
    )


@router.put("/account-variables/{name}", response_model=AccountVariableResponse)
async def update_account_variable(name: str, data: VariableUpdate, user: dict = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM account_variables WHERE user_id = ? AND name = ?", (user["id"], name))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")
        new_value = data.value if data.value is not None else existing["value"]
        new_desc = data.description if data.description is not None else existing["description"]
        cursor.execute(
            "UPDATE account_variables SET value=?, description=?, updated_at=? WHERE user_id=? AND name=?",
            (new_value, new_desc, now, user["id"], name),
        )
    return AccountVariableResponse(
        id=existing["id"], user_id=user["id"], name=name,
        value=new_value, description=new_desc,
        created_at=existing["created_at"], updated_at=now,
    )


@router.delete("/account-variables/{name}")
async def delete_account_variable(name: str, user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM account_variables WHERE user_id = ? AND name = ?", (user["id"], name))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")
        cursor.execute("DELETE FROM account_variables WHERE user_id = ? AND name = ?", (user["id"], name))
    return {"message": f"Variable '{name}' deleted"}


# ─────────────────────────────────────────────
# Prompt Variables
# ─────────────────────────────────────────────

@router.get("/prompts/{prompt_id}/variables", response_model=List[PromptVariableResponse])
async def list_prompt_variables(prompt_id: str, version: str = "v1", user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Prompt not found")
        cursor.execute(
            "SELECT * FROM prompt_variables WHERE prompt_id = ? AND version = ? ORDER BY name",
            (prompt_id, version),
        )
        return [
            PromptVariableResponse(
                id=row["id"], prompt_id=row["prompt_id"], version=row["version"],
                name=row["name"], value=row["value"], description=row["description"],
                required=bool(row["required"]), created_at=row["created_at"], updated_at=row["updated_at"],
            )
            for row in cursor.fetchall()
        ]


@router.post("/prompts/{prompt_id}/variables", response_model=PromptVariableResponse)
async def create_prompt_variable(prompt_id: str, data: VariableCreate, version: str = "v1", user: dict = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    var_id = str(uuid.uuid4())
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Prompt not found")
        cursor.execute(
            "SELECT id FROM prompt_variables WHERE prompt_id = ? AND version = ? AND name = ?",
            (prompt_id, version, data.name),
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"Variable '{data.name}' already exists for this version")
        cursor.execute(
            "INSERT INTO prompt_variables (id, prompt_id, version, name, value, description, required, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)",
            (var_id, prompt_id, version, data.name, data.value, data.description, now, now),
        )
    return PromptVariableResponse(
        id=var_id, prompt_id=prompt_id, version=version, name=data.name,
        value=data.value, description=data.description, required=False,
        created_at=now, updated_at=now,
    )


@router.put("/prompts/{prompt_id}/variables/{name}", response_model=PromptVariableResponse)
async def update_prompt_variable(prompt_id: str, name: str, data: VariableUpdate, version: str = "v1", user: dict = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM prompt_variables WHERE prompt_id = ? AND version = ? AND name = ?",
            (prompt_id, version, name),
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")
        new_value = data.value if data.value is not None else existing["value"]
        new_desc = data.description if data.description is not None else existing["description"]
        cursor.execute(
            "UPDATE prompt_variables SET value=?, description=?, updated_at=? WHERE prompt_id=? AND version=? AND name=?",
            (new_value, new_desc, now, prompt_id, version, name),
        )
    return PromptVariableResponse(
        id=existing["id"], prompt_id=prompt_id, version=version, name=name,
        value=new_value, description=new_desc, required=bool(existing["required"]),
        created_at=existing["created_at"], updated_at=now,
    )


@router.delete("/prompts/{prompt_id}/variables/{name}")
async def delete_prompt_variable(prompt_id: str, name: str, version: str = "v1", user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM prompt_variables WHERE prompt_id = ? AND version = ? AND name = ?",
            (prompt_id, version, name),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")
        cursor.execute(
            "DELETE FROM prompt_variables WHERE prompt_id = ? AND version = ? AND name = ?",
            (prompt_id, version, name),
        )
    return {"message": f"Variable '{name}' deleted"}


# ─────────────────────────────────────────────
# Combined Available Variables (for autocomplete)
# ─────────────────────────────────────────────

@router.get("/prompts/{prompt_id}/available-variables", response_model=List[AvailableVariableResponse])
async def get_available_variables(prompt_id: str, version: str = "v1", user: dict = Depends(require_auth)):
    """Get all available variables for a prompt (prompt-level + account-level)."""
    variables = []
    seen = set()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Prompt not found")
        # Prompt-level (higher priority)
        cursor.execute("SELECT * FROM prompt_variables WHERE prompt_id = ? AND version = ?", (prompt_id, version))
        for row in cursor.fetchall():
            seen.add(row["name"])
            variables.append(AvailableVariableResponse(
                name=row["name"], value=row["value"], description=row["description"],
                source="prompt", required=bool(row["required"]),
            ))
        # Account-level (lower priority)
        cursor.execute("SELECT * FROM account_variables WHERE user_id = ?", (user["id"],))
        for row in cursor.fetchall():
            if row["name"] not in seen:
                seen.add(row["name"])
                variables.append(AvailableVariableResponse(
                    name=row["name"], value=row["value"], description=row["description"],
                    source="account", required=False,
                ))
    return variables
