"""DB write helpers for memory tier inserts.

Collapses the embed/no-embed branches that used to live inline in
memory_tasks.py. Pgvector accepts NULL for the embedding column, so we
always pass it as a single parameter.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from core.storage import get_memory_db_context


def insert_memory(
    *,
    memory_id: str,
    interaction_date: str,
    entity_type: str,
    entity_id: str,
    interaction_ids: list,
    content_summary: str,
    related_entities: list,
    intents: list,
    relationships: list,
    embedding: Optional[list],
    processing_errors: dict,
) -> None:
    """INSERT a row into memories. Marks source interactions as done and
    clears their ephemeral embeddings. Idempotent on (date, entity_type, entity_id)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memories (
                id, date, primary_entity_type, primary_entity_id,
                interaction_ids, interaction_count, content_summary,
                related_entities, intents, relationships, embedding, processing_errors
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, primary_entity_type, primary_entity_id) DO NOTHING
        """, (
            memory_id, interaction_date, entity_type, entity_id,
            interaction_ids, len(interaction_ids), content_summary,
            json.dumps(related_entities), intents,
            json.dumps(relationships), embedding, json.dumps(processing_errors),
        ))

        cursor.execute("""
            UPDATE interactions SET status = 'done', embedding = NULL
            WHERE id = ANY(%s) AND status IN ('pending', 'failed')
        """, (interaction_ids,))


def insert_intelligence(
    *,
    insight_id: str,
    entity_type: str,
    entity_id: str,
    memory_ids: list,
    signals: list,
    name: str,
    content: str,
    summary: str,
    embedding: Optional[list],
    auto_approve: bool,
) -> None:
    """INSERT a row into intelligence and mark source memories as compacted."""
    status = "confirmed" if auto_approve else "draft"
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO intelligence (
                id, primary_entity_type, primary_entity_id, source_memory_ids,
                signals, name, content, summary, embedding,
                status, created_by, confirmed_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            insight_id, entity_type, entity_id, memory_ids,
            signals or [], name, content, summary, embedding,
            status, "auto", now if auto_approve else None, now, now,
        ))

        cursor.execute("""
            UPDATE memories SET compacted = TRUE, compaction_count = compaction_count + 1
            WHERE id = ANY(%s)
        """, (memory_ids,))


def insert_knowledge(
    *,
    knowledge_id: str,
    intelligence_ids: list,
    name: str,
    content: str,
    summary: str,
    embedding: Optional[list],
    tags: list,
    visibility: str = "shared",
    # ── Unified knowledge fields ──────────────────────────────────────
    signals: Optional[list] = None,
    category: str = "trade_knowledge",
    metadata: Optional[dict] = None,
    source_pathway: str = "experiential",
    source_ai_interaction_ids: Optional[list] = None,
    extraction_confidence: float = 0.5,
    evidence_breadth: int = 1,
    outcome_signal: float = 0.0,
    quality_score: Optional[float] = None,
    status: str = "active",
    version: int = 1,
) -> None:
    """INSERT a row into knowledge (unified table for all categories).

    For category 'skill'/'playbook' the content column stores the full
    agent-skills-standard SKILL.md document. If the caller passed plain text
    (LLM output or admin input), it is rendered into SKILL.md here; content
    that already carries frontmatter (e.g. marketplace imports) is stored
    verbatim."""
    import json as _json
    from memory_skill_md import SKILL_MD_CATEGORIES, is_skill_md, render_skill_md
    now = datetime.now(timezone.utc).isoformat()
    if category in SKILL_MD_CATEGORIES and not is_skill_md(content):
        content = render_skill_md(
            name=name,
            category=category,
            description=summary or content,
            body=content,
            metadata=metadata,
            signals=signals,
            tags=tags,
            version=version,
        )
    # Stamp embedding provenance (model / dimensions / version / timestamp) so
    # candidate discovery and the resumable backfill know how each record was
    # embedded. Idempotent: a re-embed with the same vector re-stamps the same
    # block. No-op when no embedding was produced.
    if embedding:
        try:
            from memory_embedding import merge_embedding_metadata, current_embedding_model
            metadata = merge_embedding_metadata(
                metadata or {}, model=current_embedding_model(), vector=embedding
            )
        except Exception:
            pass
    md = _json.dumps(metadata) if metadata else "{}"
    ai_ids = source_ai_interaction_ids or []
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO knowledge (
                id, source_intelligence_ids, signals, name, content, summary,
                embedding, visibility, tags, created_at, updated_at,
                category, metadata, source_pathway, source_ai_interaction_ids,
                extraction_confidence, evidence_breadth, outcome_signal,
                quality_score, status, version
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
        """, (
            knowledge_id, intelligence_ids, signals or [], name, content, summary,
            embedding, visibility, tags, now, now,
            category, md, source_pathway, ai_ids,
            extraction_confidence, evidence_breadth, outcome_signal,
            quality_score, status, version,
        ))

    # Creation-time consolidation hook (opt-in, default off). Fire-and-forget:
    # enqueues an async preview job so generation never waits on a consolidation
    # LLM call. Only fires when knowledge_hygiene_creation_time_enabled=true.
    _maybe_enqueue_creation_time_consolidation(knowledge_id, category, status)


def _maybe_enqueue_creation_time_consolidation(knowledge_id: str, category: str, status: str) -> None:
    """Enqueue a creation-time consolidation preview when the feature is enabled.

    Non-blocking and best-effort: any failure to enqueue is logged and swallowed
    so knowledge creation can never regress on a consolidation hiccup. The actual
    candidate discovery + preview runs in the queue worker.
    """
    if status in ("draft", "retired") or not knowledge_id:
        return
    try:
        from services.config_helpers import get_memory_settings
        settings = get_memory_settings() or {}
        if not settings.get("knowledge_hygiene_creation_time_enabled", False):
            return
        if not settings.get("knowledge_hygiene_enabled", True):
            return
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        if loop is None or not loop.is_running():
            return
        from memory.queue import knowledge_queue
        loop.create_task(knowledge_queue.add(
            "creation_time_consolidation",
            {"knowledge_id": knowledge_id, "category": category},
            {"priority": 3},
        ))
    except Exception:
        logging.getLogger(__name__).debug(
            "creation-time consolidation enqueue skipped for %s", knowledge_id, exc_info=True
        )


def update_knowledge_quality(knowledge_id: str, quality_score: float) -> None:
    """Recompute and persist quality_score for a knowledge record."""
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE knowledge SET quality_score = %s, updated_at = %s WHERE id = %s
        """, (quality_score, now, knowledge_id))


def log_pipeline_run(
    job: str,
    outcome: str,
    *,
    reason_code: Optional[str] = None,
    records_created: int = 0,
    detail: Optional[dict] = None,
    trigger: str = "scheduled",
) -> None:
    """Record one pipeline run for observability. Best-effort — never raises, so
    it can wrap generation code without risking the pipeline."""
    import json as _json
    import logging
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_pipeline_runs (job, outcome, reason_code, records_created, detail, trigger)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (job, outcome, reason_code, records_created, _json.dumps(detail or {}), trigger))
    except Exception as e:
        logging.getLogger(__name__).warning(f"log_pipeline_run failed ({job}/{outcome}): {e}")


def append_knowledge_feedback(knowledge_id: str, outcome: str, notes: Optional[str] = None) -> None:
    """Append a feedback entry and increment success/failure counter."""
    import json as _json
    now = datetime.now(timezone.utc).isoformat()
    entry = _json.dumps({"outcome": outcome, "notes": notes, "timestamp": now})
    counter_col = "success_count" if outcome == "success" else "failure_count"
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE knowledge
            SET feedback_notes = feedback_notes || %s::jsonb,
                {counter_col} = {counter_col} + 1,
                updated_at = %s
            WHERE id = %s
        """, (entry, now, knowledge_id))
