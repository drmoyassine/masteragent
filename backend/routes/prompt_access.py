"""Shared prompt ownership checks used by prompt-adjacent routers."""
from fastapi import HTTPException


def require_prompt_owner(cursor, prompt_id: str, user_id: str) -> dict:
    cursor.execute(
        "SELECT * FROM prompts WHERE id = %s AND user_id = %s",
        (prompt_id, user_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return dict(row)
