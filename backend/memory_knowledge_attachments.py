"""Asynchronous extraction and proposal helpers for knowledge attachments."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)

MAX_EXTRACTED_CHARS = 250_000


def _load_attachment(attachment_id: str) -> Dict[str, Any] | None:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM knowledge_attachments WHERE id=%s", (attachment_id,))
        row = cur.fetchone()
    return dict(row) if row else None


async def extract_attachment(attachment_id: str, max_pages: int = 200) -> Dict[str, Any]:
    """Parse one staged file using the shared PDF/DOCX/XLSX/vision pipeline."""
    attachment = _load_attachment(attachment_id)
    if not attachment:
        return {"status": "missing", "attachment_id": attachment_id}

    with get_memory_db_context() as conn:
        conn.cursor().execute(
            "UPDATE knowledge_attachments SET status='extracting', updated_at=NOW() WHERE id=%s AND status IN ('queued','failed')",
            (attachment_id,),
        )

    try:
        from services.processing import parse_document

        async def report_page(current: int, total: int) -> None:
            with get_memory_db_context() as progress_conn:
                progress_conn.cursor().execute(
                    "UPDATE knowledge_attachments SET extraction=%s::jsonb, updated_at=NOW() WHERE id=%s",
                    (json.dumps({"stage": "extracting", "current_page": current, "total_pages": total, "parser": "shared_document_pipeline"}), attachment_id),
                )

        parsed = await parse_document(
            bytes(attachment["content"]), attachment["filename"], attachment["mime_type"],
            max_pages=max_pages, progress_callback=report_page,
        )
        text = (parsed.get("text") or "").strip()
        extraction = {
            "pages": parsed.get("pages", 0),
            "parsed_pages": parsed.get("parsed_pages", parsed.get("pages", 0)),
            "page_limit": max_pages,
            "pages_omitted": max(0, int(parsed.get("pages", 0) or 0) - int(parsed.get("parsed_pages", parsed.get("pages", 0)) or 0)),
            "has_images": bool(parsed.get("has_images")),
            "truncated": len(text) > MAX_EXTRACTED_CHARS,
            "parser": "shared_document_pipeline",
        }
        if len(text) > MAX_EXTRACTED_CHARS:
            text = text[:MAX_EXTRACTED_CHARS]
        with get_memory_db_context() as conn:
            conn.cursor().execute(
                """UPDATE knowledge_attachments
                   SET extracted_text=%s, extraction=%s::jsonb, status=%s, updated_at=NOW()
                   WHERE id=%s""",
                (text, json.dumps(extraction), "ready" if text else "failed", attachment_id),
            )
        return {"attachment_id": attachment_id, "status": "ready" if text else "failed", **extraction}
    except Exception as exc:
        logger.exception("Knowledge attachment extraction failed for %s", attachment_id)
        with get_memory_db_context() as conn:
            conn.cursor().execute(
                "UPDATE knowledge_attachments SET status='failed', extraction=%s::jsonb, updated_at=NOW() WHERE id=%s",
                (json.dumps({"error": str(exc), "parser": "shared_document_pipeline"}), attachment_id),
            )
        raise


def load_ready_attachment_text(attachment_ids: List[str]) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, filename, mime_type, size_bytes, sha256, extracted_text, extraction, status
               FROM knowledge_attachments WHERE id = ANY(%s) ORDER BY created_at ASC""",
            (attachment_ids,),
        )
        return [dict(row) for row in cur.fetchall()]


def attachment_source_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
