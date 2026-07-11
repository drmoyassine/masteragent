"""memory_embedding_backfill.py — Resumable, idempotent embedding backfill.

Re-embeds active knowledge records whose ``metadata.embedding.version`` does
not match the configured ``knowledge_hygiene_embedding_version`` (including
legacy rows with no provenance block at all). It never mutates content, status,
or any non-embedding field, so it is safe to run against a live production
table and safe to re-run (idempotent).

Batched (default 50) with per-record error capture so a single bad record
never aborts the run. A queue worker calls ``run_embedding_backfill`` and
records the processed/succeeded/failed counts on the hygiene run row.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from core.storage import get_memory_db_context
from memory_embedding import (
    EMBEDDING_VERSION,
    embed_knowledge_record,
    get_embedding_version,
)

logger = logging.getLogger(__name__)


def _configured_version(settings: Optional[Dict[str, Any]] = None) -> int:
    if settings is None:
        try:
            from services.config_helpers import get_memory_settings
            settings = get_memory_settings() or {}
        except Exception:
            settings = {}
    try:
        return int(settings.get("knowledge_hygiene_embedding_version", EMBEDDING_VERSION))
    except (TypeError, ValueError):
        return EMBEDDING_VERSION


def _select_stale_rows(batch_size: int, configured_version: int, offset: int = 0) -> List[Dict[str, Any]]:
    """Active records whose embedding version is missing/stale, oldest first.

    A row is stale when it has no embedding, or its recorded version differs
    from the configured version. Bounded by ``batch_size`` for resumability.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        # metadata.embedding is JSONB; records without the block or with a
        # different version are candidates.
        cursor.execute(
            """
            SELECT id, name, category, content, summary, signals, tags, metadata,
                   (metadata->'embedding'->>'version')::int AS emb_version
            FROM knowledge
            WHERE status = 'active'
              AND category IN ('best_practices','lessons_learned','trade_knowledge','skill','playbook')
            ORDER BY created_at ASC, id ASC
            LIMIT %s OFFSET %s
            """,
            (batch_size, offset),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    stale: List[Dict[str, Any]] = []
    for row in rows:
        version = row.get("emb_version")
        if version is None:
            version = get_embedding_version(row)
        if version != configured_version:
            stale.append(row)
    return stale


async def run_embedding_backfill(
    *,
    batch_size: int = 50,
    max_records: Optional[int] = None,
    configured_version: Optional[int] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """Re-embed stale records in batches. Idempotent and resumable.

    Processes up to ``max_records`` records (default unbounded → drains all
    stale rows in ``batch_size`` batches). Returns a counts dict::

        {"processed": N, "succeeded": N, "failed": N,
         "configured_version": V, "batches": B}

    Each record is re-embedded and its ``metadata.embedding`` block is updated
    only after a fresh version check inside the same UPDATE, so a concurrent
    backfill or consolidation cannot clobber a newer embedding.
    """
    cv = configured_version if configured_version is not None else _configured_version(settings)
    processed = succeeded = failed = 0
    batches = 0
    seen = 0

    while True:
        if max_records is not None and seen >= max_records:
            break
        remaining = None
        if max_records is not None:
            remaining = max_records - seen
        this_batch = min(batch_size, remaining) if remaining is not None else batch_size

        rows = _select_stale_rows(this_batch, cv, offset=0)
        if not rows:
            break

        for row in rows:
            processed += 1
            seen += 1
            try:
                vector, _model, updated_metadata = await embed_knowledge_record(row, version=cv)
                if not vector:
                    failed += 1
                    continue
                _apply_embedding_update(row["id"], vector, updated_metadata, cv)
                succeeded += 1
            except Exception as exc:  # never abort the whole run on one record
                failed += 1
                logger.warning("Embedding backfill failed for %s: %s", row.get("id"), exc)

        batches += 1
        if len(rows) < this_batch:
            break

    counts = {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "configured_version": cv,
        "batches": batches,
    }
    logger.info("Embedding backfill complete: %s", counts)
    return counts


def _apply_embedding_update(knowledge_id: str, vector: List[float], metadata: Dict[str, Any], version: int) -> None:
    """Persist the new embedding + stamped metadata under a version guard.

    The UPDATE is conditional on the row still being stale at the configured
    version, so a concurrent consolidation that retired or re-versioned the
    row wins instead of being clobbered.
    """
    md = json.dumps(metadata) if metadata else "{}"
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE knowledge
            SET embedding = %s,
                metadata = jsonb_set(
                    COALESCE(metadata, '{}'::jsonb),
                    '{embedding}',
                    %s::jsonb
                ),
                updated_at = NOW()
            WHERE id = %s
              AND status = 'active'
              AND COALESCE((metadata->'embedding'->>'version')::int, 1) <> %s
            """,
            (vector, json.dumps(metadata.get("embedding") or {}), knowledge_id, version),
        )


def preview_backfill(configured_version: Optional[int] = None) -> Dict[str, Any]:
    """Return how many active records are stale vs current (settings UI gauge).

    Pure read — used by the settings endpoint to show coverage before an admin
    kicks off the backfill.
    """
    cv = configured_version if configured_version is not None else _configured_version()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE COALESCE((metadata->'embedding'->>'version')::int, 1) = %s) AS current,
              COUNT(*) FILTER (WHERE COALESCE((metadata->'embedding'->>'version')::int, 1) <> %s) AS stale
            FROM knowledge
            WHERE status = 'active'
              AND category IN ('best_practices','lessons_learned','trade_knowledge','skill','playbook')
            """,
            (cv, cv),
        )
        row = cursor.fetchone() or {}
    total = int(row.get("total") or 0)
    current = int(row.get("current") or 0)
    stale = int(row.get("stale") or 0)
    return {
        "total": total,
        "current_version": cv,
        "compatible": current,
        "stale": stale,
        "coverage": round(current / total, 4) if total else 0.0,
    }
