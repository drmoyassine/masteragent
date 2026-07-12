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


def _embedding_provenance(embedding, *, knowledge: bool = False):
    if not embedding:
        return (None, None, None, None)
    from memory_embedding import current_embedding_model, EMBEDDING_VERSION
    return (
        current_embedding_model(), EMBEDDING_VERSION if knowledge else 1,
        len(embedding), datetime.now(timezone.utc).isoformat(),
    )


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
    """INSERT a memory and retain source embeddings for semantic lineage."""
    emodel, eversion, edims, embedded_at = _embedding_provenance(embedding)
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memories (
                id, date, primary_entity_type, primary_entity_id,
                interaction_ids, interaction_count, content_summary,
                related_entities, intents, relationships, embedding, processing_errors,
                embedding_model, embedding_version, embedding_dimensions, embedded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, primary_entity_type, primary_entity_id) DO NOTHING
        """, (
            memory_id, interaction_date, entity_type, entity_id,
            interaction_ids, len(interaction_ids), content_summary,
            json.dumps(related_entities), intents,
            json.dumps(relationships), embedding, json.dumps(processing_errors),
            emodel, eversion, edims, embedded_at,
        ))

        cursor.execute("""
            UPDATE interactions SET status = 'done'
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
    emodel, eversion, edims, embedded_at = _embedding_provenance(embedding)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO intelligence (
                id, primary_entity_type, primary_entity_id, source_memory_ids,
                signals, name, content, summary, embedding,
                status, created_by, confirmed_at, created_at, updated_at,
                embedding_model, embedding_version, embedding_dimensions, embedded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            insight_id, entity_type, entity_id, memory_ids,
            signals or [], name, content, summary, embedding,
            status, "auto", now if auto_approve else None, now, now,
            emodel, eversion, edims, embedded_at,
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
    source_links: Optional[list] = None,
    attachment_ids: Optional[list] = None,
    extraction_confidence: float = 0.5,
    evidence_breadth: int = 1,
    outcome_signal: float = 0.0,
    quality_score: Optional[float] = None,
    status: str = "active",
    version: int = 1,
    approved_by_type: Optional[str] = None,
    approved_by_id: Optional[str] = None,
    approval_origin: Optional[str] = None,
    generation_state: str = "ready",
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
    facet_info = (metadata or {}).get("facet_extraction") or {}
    facet_status = facet_info.get("status") or ("explicit" if (metadata or {}).get("facets") else "no_facet")
    ai_ids = source_ai_interaction_ids or []
    emodel, eversion, edims, embedded_at = _embedding_provenance(embedding, knowledge=True)
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO knowledge (
                id, source_intelligence_ids, signals, name, content, summary,
                embedding, visibility, tags, created_at, updated_at,
                category, metadata, source_pathway, source_ai_interaction_ids,
                extraction_confidence, evidence_breadth, outcome_signal,
                quality_score, status, version,
                embedding_model, embedding_version, embedding_dimensions, embedded_at,
                approved_at, approved_by_type, approved_by_id, approval_origin, generation_state,
                facet_schema_version, facet_status, facet_provenance
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s
            )
        """, (
            knowledge_id, intelligence_ids, signals or [], name, content, summary,
            embedding, visibility, tags, now, now,
            category, md, source_pathway, ai_ids,
            extraction_confidence, evidence_breadth, outcome_signal,
            quality_score, status, version,
            emodel, eversion, edims, embedded_at,
            now if status == "active" else None,
            (approved_by_type or "system") if status == "active" else None,
            approved_by_id if status == "active" else None,
            (approval_origin or "generation_policy") if status == "active" else None,
            generation_state,
            1, facet_status, _json.dumps(facet_info),
        ))

        # Normalized provenance is authoritative; arrays remain compatibility fields.
        for sid in intelligence_ids or []:
            cursor.execute("""
                INSERT INTO knowledge_source_links(knowledge_id,source_type,source_id,source_role)
                VALUES (%s,'intelligence',%s,'primary') ON CONFLICT DO NOTHING
            """, (knowledge_id, sid))
        for sid in ai_ids:
            cursor.execute("""
                INSERT INTO knowledge_source_links(knowledge_id,source_type,source_id,source_role)
                VALUES (%s,'interaction',%s,'context') ON CONFLICT DO NOTHING
            """, (knowledge_id, sid))
        for source in source_links or []:
            source_type = source.get("source_type")
            source_id = source.get("source_id")
            if source_type not in {"interaction", "memory", "intelligence", "telemetry"} or not source_id:
                continue
            cursor.execute("""
                INSERT INTO knowledge_source_links(knowledge_id,source_type,source_id,source_role)
                VALUES (%s,%s,%s,'primary') ON CONFLICT DO NOTHING
            """, (knowledge_id, source_type, source_id))
        if attachment_ids:
            attachment_ids = list(dict.fromkeys(str(a) for a in attachment_ids))
            cursor.execute(
                """SELECT id FROM knowledge_attachments
                   WHERE id = ANY(%s) AND knowledge_id IS NULL AND status = 'ready'""",
                (attachment_ids,),
            )
            found = {str(row["id"]) for row in cursor.fetchall()}
            missing = [aid for aid in attachment_ids if aid not in found]
            if missing:
                raise ValueError(f"Attachment(s) are missing, expired, or already linked: {', '.join(missing)}")
            for aid in attachment_ids:
                cursor.execute(
                    "UPDATE knowledge_attachments SET knowledge_id=%s, status='linked', updated_at=NOW() WHERE id=%s",
                    (knowledge_id, aid),
                )
                cursor.execute("""
                    INSERT INTO knowledge_source_links(knowledge_id,source_type,source_id,source_role)
                    VALUES (%s,'attachment',%s,'evidence') ON CONFLICT DO NOTHING
                """, (knowledge_id, aid))

    from memory_quality import recalculate_knowledge_quality
    recalculate_knowledge_quality(knowledge_id)

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
) -> Optional[str]:
    """Record one pipeline run for observability. Best-effort — never raises, so
    it can wrap generation code without risking the pipeline."""
    import json as _json
    import logging
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            status = {"started": "running", "completed": "completed", "created": "completed", "revised": "completed", "stopped": "paused", "failed": "failed", "blocked": "blocked", "skipped": "skipped"}.get(outcome, outcome)
            cursor.execute("""
                INSERT INTO memory_pipeline_runs (job, outcome, reason_code, records_created, detail, trigger, status,
                    progress_total, progress_completed, progress_failed, estimated_tokens, estimated_cost_usd,
                    started_at, updated_at, finished_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s,
                    COALESCE((%s::jsonb->>'progress_total')::int, 0),
                    COALESCE((%s::jsonb->>'progress_completed')::int, 0),
                    COALESCE((%s::jsonb->>'progress_failed')::int, 0),
                    (%s::jsonb->>'estimated_tokens')::bigint,
                    (%s::jsonb->>'estimated_cost_usd')::numeric,
                    CASE WHEN %s = 'running' THEN NOW() ELSE NULL END,
                    NOW(),
                    CASE WHEN %s IN ('completed','failed','blocked','skipped') THEN NOW() ELSE NULL END)
                RETURNING id
            """, (job, outcome, reason_code, records_created, _json.dumps(detail or {}), trigger, status,
                   _json.dumps(detail or {}), _json.dumps(detail or {}), _json.dumps(detail or {}),
                   _json.dumps(detail or {}), _json.dumps(detail or {}), status, status))
            row = cursor.fetchone()
            return str(row["id"]) if row else None
    except Exception as e:
        logging.getLogger(__name__).warning(f"log_pipeline_run failed ({job}/{outcome}): {e}")
        return None


def update_pipeline_run(run_id: str, *, status: Optional[str] = None,
                        outcome: Optional[str] = None, reason_code: Optional[str] = None,
                        records_created: Optional[int] = None, progress_total: Optional[int] = None,
                        progress_completed: Optional[int] = None, progress_failed: Optional[int] = None,
                        detail: Optional[dict] = None, estimated_tokens: Optional[int] = None,
                        estimated_cost_usd: Optional[float] = None) -> None:
    """Update live status for a running maintenance job. Best effort only."""
    import json as _json
    import logging
    try:
        sets, params = ["updated_at = NOW()"], []
        for column, value in (("status", status), ("outcome", outcome), ("reason_code", reason_code),
                              ("records_created", records_created), ("progress_total", progress_total),
                              ("progress_completed", progress_completed), ("progress_failed", progress_failed),
                              ("estimated_tokens", estimated_tokens), ("estimated_cost_usd", estimated_cost_usd)):
            if value is not None:
                sets.append(f"{column} = %s"); params.append(value)
        if detail is not None:
            sets.append("detail = detail || %s::jsonb"); params.append(_json.dumps(detail))
        if status in {"completed", "failed", "blocked", "cancelled", "paused"}:
            sets.append("finished_at = COALESCE(finished_at, NOW())")
        params.append(run_id)
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE memory_pipeline_runs SET {', '.join(sets)} WHERE id = %s", params)
    except Exception as e:
        logging.getLogger(__name__).warning(f"update_pipeline_run failed ({run_id}): {e}")


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
    from memory_quality import recalculate_knowledge_quality
    recalculate_knowledge_quality(knowledge_id)
