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
    current_embedding_model,
    embed_knowledge_record,
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


def _select_stale_rows(
    batch_size: int,
    configured_version: int,
    configured_model: str,
    exclude_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Active records whose embedding version is missing/stale, oldest first.

    A row is stale when it has no embedding, or its recorded version differs
    from the configured version. Bounded by ``batch_size`` for resumability.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        # Filter stale records in SQL. Filtering only after LIMIT would stop
        # early whenever the first page happened to contain current records.
        cursor.execute(
            """
            SELECT id, name, category, content, summary, signals, tags, metadata
            FROM knowledge
            WHERE status = 'active'
              AND category IN ('best_practices','lessons_learned','trade_knowledge','skill','playbook')
              AND NOT (id = ANY(%s))
              AND (
                    embedding IS NULL
                 OR COALESCE(metadata->'embedding'->>'version', '1') <> %s
                 OR COALESCE(metadata->'embedding'->>'model', '') <> %s
                 OR metadata->'embedding'->>'dimensions' IS DISTINCT FROM vector_dims(embedding)::text
              )
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            """,
            (exclude_ids or [], str(configured_version), configured_model or "", batch_size),
        )
        return [dict(r) for r in cursor.fetchall()]


async def run_embedding_backfill(
    *,
    batch_size: int = 50,
    max_records: Optional[int] = None,
    configured_version: Optional[int] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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
    configured_model = current_embedding_model()
    processed = succeeded = failed = 0
    batches = 0
    seen = 0
    attempted_ids: List[str] = []

    while True:
        if max_records is not None and seen >= max_records:
            break
        remaining = None
        if max_records is not None:
            remaining = max_records - seen
        this_batch = min(batch_size, remaining) if remaining is not None else batch_size

        rows = _select_stale_rows(this_batch, cv, configured_model, attempted_ids)
        if not rows:
            break

        for row in rows:
            processed += 1
            seen += 1
            attempted_ids.append(row["id"])
            try:
                vector, _model, updated_metadata = await embed_knowledge_record(row, version=cv)
                if not vector:
                    failed += 1
                    continue
                if _apply_embedding_update(row["id"], vector, updated_metadata, cv, configured_model):
                    succeeded += 1
                else:
                    # A concurrent writer made the row current or retired it.
                    logger.info("Embedding backfill skipped concurrently changed row %s", row["id"])
            except Exception as exc:  # never abort the whole run on one record
                failed += 1
                logger.warning("Embedding backfill failed for %s: %s", row.get("id"), exc)

        batches += 1
        if len(rows) < this_batch:
            break

    tier_counts = await _backfill_source_tiers(batch_size=batch_size, max_records=max_records)
    counts = {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "configured_version": cv,
        "batches": batches,
        "tiers": tier_counts,
    }
    logger.info("Embedding backfill complete: %s", counts)
    return counts


async def _backfill_source_tiers(*, batch_size: int, max_records: Optional[int]) -> Dict[str, Dict[str, int]]:
    """Persist missing/stale embeddings for tiers 0–2 using their canonical text."""
    from memory_services import generate_embedding
    model = current_embedding_model()
    specs = {
        "interactions": ("content", "timestamp"),
        "memories": ("content_summary", "created_at"),
        "intelligence": ("COALESCE(name,'') || '. ' || COALESCE(summary,'') || ' ' || COALESCE(content,'')", "created_at"),
    }
    results: Dict[str, Dict[str, int]] = {}
    for table, (text_expr, order_col) in specs.items():
        processed = succeeded = failed = 0
        attempted: set[str] = set()
        while max_records is None or processed < max_records:
            limit = min(batch_size, max_records - processed) if max_records is not None else batch_size
            with get_memory_db_context() as conn:
                cur = conn.cursor()
                cur.execute(f"""
                    SELECT id, {text_expr} AS embedding_text FROM {table}
                    WHERE NOT (id = ANY(%s)) AND ({text_expr}) IS NOT NULL
                      AND (embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                           OR embedding_dimensions IS DISTINCT FROM vector_dims(embedding))
                    ORDER BY {order_col} ASC, id ASC LIMIT %s
                """, (list(attempted), model, limit))
                rows = [dict(r) for r in cur.fetchall()]
            if not rows:
                break
            for row in rows:
                attempted.add(row["id"]); processed += 1
                try:
                    vector = await generate_embedding(str(row.get("embedding_text") or ""))
                    if not vector:
                        failed += 1; continue
                    with get_memory_db_context() as conn:
                        cur = conn.cursor()
                        cur.execute(f"""
                            UPDATE {table} SET embedding=%s::vector,embedding_model=%s,
                                embedding_version=1,embedding_dimensions=%s,embedded_at=NOW()
                            WHERE id=%s
                        """, (vector, model, len(vector), row["id"]))
                    succeeded += 1
                except Exception as exc:
                    failed += 1
                    logger.warning("%s embedding backfill failed for %s: %s", table, row["id"], exc)
            if len(rows) < limit:
                break
        results[table] = {"processed": processed, "succeeded": succeeded, "failed": failed}
    return results


def _apply_embedding_update(
    knowledge_id: str,
    vector: List[float],
    metadata: Dict[str, Any],
    version: int,
    configured_model: str,
) -> bool:
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
                embedding_model = %s,
                embedding_version = %s,
                embedding_dimensions = %s,
                embedded_at = NOW(),
                metadata = jsonb_set(
                    COALESCE(metadata, '{}'::jsonb),
                    '{embedding}',
                    %s::jsonb
                ),
                updated_at = NOW()
            WHERE id = %s
              AND (
                    embedding IS NULL
                 OR COALESCE(metadata->'embedding'->>'version', '1') <> %s
                 OR COALESCE(metadata->'embedding'->>'model', '') <> %s
                 OR metadata->'embedding'->>'dimensions' IS DISTINCT FROM vector_dims(embedding)::text
              )
            """,
            (vector, configured_model, version, len(vector),
             json.dumps(metadata.get("embedding") or {}), knowledge_id,
             str(version), configured_model or ""),
        )
        return cursor.rowcount == 1


def preview_backfill(configured_version: Optional[int] = None) -> Dict[str, Any]:
    """Return how many active records are stale vs current (settings UI gauge).

    Pure read — used by the settings endpoint to show coverage before an admin
    kicks off the backfill.
    """
    cv = configured_version if configured_version is not None else _configured_version()
    configured_model = current_embedding_model()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE embedding IS NOT NULL
                 AND COALESCE(metadata->'embedding'->>'version', '1') = %s
                 AND COALESCE(metadata->'embedding'->>'model', '') = %s
                 AND metadata->'embedding'->>'dimensions' IS NOT DISTINCT FROM vector_dims(embedding)::text) AS current,
              COUNT(*) FILTER (WHERE embedding IS NULL
                 OR COALESCE(metadata->'embedding'->>'version', '1') <> %s
                 OR COALESCE(metadata->'embedding'->>'model', '') <> %s
                 OR metadata->'embedding'->>'dimensions' IS DISTINCT FROM vector_dims(embedding)::text) AS stale
            FROM knowledge
            WHERE category IN ('best_practices','lessons_learned','trade_knowledge','skill','playbook')
            """,
            (str(cv), configured_model or "", str(cv), configured_model or ""),
        )
        row = cursor.fetchone() or {}
    total = int(row.get("total") or 0)
    current = int(row.get("current") or 0)
    stale = int(row.get("stale") or 0)
    tiers = {"knowledge": {"total": total, "compatible": current, "stale": stale}}
    for table in ("interactions", "memories", "intelligence"):
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE embedding IS NOT NULL AND embedding_model=%s
                         AND embedding_dimensions=vector_dims(embedding)) AS compatible
                FROM {table}
            """, (configured_model,))
            tier = cursor.fetchone() or {}
        tier_total = int(tier.get("total") or 0)
        tier_current = int(tier.get("compatible") or 0)
        tiers[table] = {
            "total": tier_total, "compatible": tier_current,
            "stale": tier_total - tier_current,
            "coverage": round(tier_current / tier_total, 4) if tier_total else 0.0,
        }
    all_total = sum(item["total"] for item in tiers.values())
    all_current = sum(item["compatible"] for item in tiers.values())
    return {
        "total": all_total,
        "current_version": cv,
        "compatible": all_current,
        "stale": all_total - all_current,
        "coverage": round(all_current / all_total, 4) if all_total else 0.0,
        "tiers": tiers,
    }
