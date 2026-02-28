"""
routes/templates.py — Template endpoints (no auth required)
"""
import json
import logging

from fastapi import APIRouter, HTTPException
from core.db import get_db_context

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/templates")
async def get_templates():
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM templates ORDER BY created_at")
        rows = cursor.fetchall()
        templates = []
        for row in rows:
            t = dict(row)
            t["sections"] = json.loads(t["sections"])
            templates.append(t)
        return templates


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Template not found")
        t = dict(row)
        t["sections"] = json.loads(t["sections"])
        return t
