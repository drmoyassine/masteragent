"""Consolidation, decay, and quality score recomputation for unified knowledge.

Runs periodically (configurable interval) to:
1. Merge semantically similar knowledge records
2. Refine playbooks with new evidence
3. Retire stale records based on decay gauges
4. Recompute quality scores for all active records
"""
import json
import logging
from datetime import datetime, timezone

from core.storage import get_memory_db_context
from memory_services import get_memory_settings
from memory_dedup import compute_quality_score
from services.llm import parse_llm_json
from memory_db_writes import update_knowledge_quality
from memory_helpers import _get_entity_type_config

logger = logging.getLogger(__name__)


async def run_consolidation():
    """Run all consolidation + decay tasks."""
    settings = get_memory_settings()
    consolidation_threshold = settings.get("consolidation_similarity_threshold", 0.80)

    logger.info("Starting consolidation run")
    await _consolidate_duplicates(consolidation_threshold)
    _apply_decay()
    _recompute_quality_scores()
    logger.info("Consolidation run complete")


async def _consolidate_duplicates(threshold: float):
    """Find and merge semantically similar knowledge records with the same category."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        # Find candidate pairs: same category, high cosine similarity, both active
        cursor.execute("""
            SELECT a.id AS aid, b.id AS bid,
                   a.category, a.merge_count AS a_mc, b.merge_count AS b_mc,
                   1 - (a.embedding <=> b.embedding) AS similarity
            FROM knowledge a
            JOIN knowledge b ON a.id < b.id
              AND a.category = b.category
              AND a.status = 'active' AND b.status = 'active'
              AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
            WHERE 1 - (a.embedding <=> b.embedding) > %s
            ORDER BY similarity DESC
            LIMIT 50
        """, (threshold,))
        pairs = [dict(r) for r in cursor.fetchall()]

    if not pairs:
        logger.info("No duplicate pairs found for consolidation")
        return

    merged = 0
    for p in pairs:
        # Keep the one with higher merge_count (more established)
        keep_id, retire_id = (p["aid"], p["bid"]) if p["a_mc"] >= p["b_mc"] else (p["bid"], p["aid"])

        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                UPDATE knowledge
                SET merge_count = merge_count + 1,
                    last_merged_at = %s,
                    updated_at = %s
                WHERE id = %s
            """, (now, now, keep_id))
            cursor.execute("""
                UPDATE knowledge SET status = 'retired', updated_at = %s WHERE id = %s
            """, (now, retire_id))
            # Refine playbook if the kept record is a playbook
            cursor.execute("SELECT category FROM knowledge WHERE id = %s", (keep_id,))
            cat_row = cursor.fetchone()
        if cat_row and dict(cat_row).get("category") == "playbook":
            await _refine_playbook(keep_id)
        merged += 1

    logger.info(f"Consolidated {merged} duplicate pairs")


async def _refine_playbook(keep_id: str):
    """Re-run LLM to update a playbook's steps and trigger_conditions after a merge event."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, content, metadata, merge_count, category, version FROM knowledge WHERE id = %s",
            (keep_id,),
        )
        row = cursor.fetchone()
    if not row or row.get("category") != "playbook":
        return

    metadata = row["metadata"] or {}
    existing_steps = metadata.get("steps", [])

    system_prompt = (
        "You are refining an existing playbook based on accumulated evidence. "
        "Review the current playbook and update steps and trigger conditions if the new evidence "
        "warrants changes. Keep existing structure unless clearly superseded.\n\n"
        'Return JSON: {"steps": [{"order": N, "action": "..."}], '
        '"trigger_conditions": [...], "confidence": 0.0-1.0}'
    )

    try:
        from memory_services import call_llm
        result_text = await call_llm(
            f"Current playbook: {row['content']}\n"
            f"Existing steps: {json.dumps(existing_steps)}\n"
            f"Merge count (evidence accumulations): {row['merge_count']}",
            system_prompt=system_prompt,
            max_tokens=600,
            task_type="knowledge_generation",
        )
        result = parse_llm_json(result_text, context="playbook_refinement")
        metadata["steps"] = result.get("steps", existing_steps)
        metadata["trigger_conditions"] = result.get(
            "trigger_conditions", metadata.get("trigger_conditions", [])
        )

        # Re-render the SKILL.md document so the content column stays the
        # canonical standard-format representation after refinement.
        from memory_skill_md import parse_skill_md, render_skill_md, is_skill_md
        body = row["content"] or ""
        description = ""
        if is_skill_md(body):
            try:
                parsed = parse_skill_md(body)
                description = parsed["description"]
                body = parsed["body"]
            except ValueError:
                pass
        new_content = render_skill_md(
            name=row["name"],
            category="playbook",
            description=description or (body or "")[:1024],
            body="",  # steps/triggers carry the procedure; keep body from description sections
            metadata=metadata,
            version=(row.get("version") or 1) + 1,
        )

        now = datetime.now(timezone.utc).isoformat()
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE knowledge SET metadata = %s, content = %s, version = version + 1, updated_at = %s WHERE id = %s",
                (json.dumps(metadata), new_content, now, keep_id),
            )
        logger.info(f"Refined playbook {keep_id} after merge")
    except Exception as e:
        logger.warning(f"Playbook refinement failed for {keep_id}: {e}")


def _apply_decay():
    """Retire stale knowledge records based on configurable decay gauges."""
    now = datetime.now(timezone.utc)

    # Get all entity types with their decay configs
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT entity_type FROM memory_entity_type_config")
        entity_types = [r["entity_type"] for r in cursor.fetchall()]

    retired = 0
    for entity_type in entity_types:
        config = _get_entity_type_config(entity_type)
        max_inactive_days = config.get("decay_max_inactive_days", 90)
        min_interactions = config.get("decay_min_interactions_since_trigger", 100)

        cutoff = (now - __import__('datetime').timedelta(days=max_inactive_days)).isoformat()

        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            # Retire playbook-category records for this entity type that haven't been updated
            cursor.execute("""
                UPDATE knowledge
                SET status = 'retired', updated_at = %s
                WHERE status = 'active'
                  AND category IN ('playbook', 'skill')
                  AND metadata->>'entity_type' = %s
                  AND updated_at < %s
            """, (now.isoformat(), entity_type, cutoff))
            retired += cursor.rowcount

    if retired:
        logger.info(f"Decay retired {retired} stale records")


def _recompute_quality_scores():
    """Batch recompute quality scores for all active knowledge records."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, category, evidence_breadth, outcome_signal,
                   extraction_confidence, merge_count, created_at
            FROM knowledge
            WHERE status = 'active' AND embedding IS NOT NULL
        """)
        records = [dict(r) for r in cursor.fetchall()]

    now = datetime.now(timezone.utc)
    updated = 0
    for r in records:
        created = r.get("created_at")
        days_old = 0.0
        if created:
            try:
                created_dt = created if isinstance(created, datetime) else datetime.fromisoformat(str(created))
                days_old = (now - created_dt).days
            except Exception:
                pass

        # Normalize evidence_breadth: assume extraction_min_entities = 3 default
        eb = r.get("evidence_breadth", 1)
        eb_norm = min(eb / 10.0, 1.0)

        quality = compute_quality_score(
            evidence_breadth_norm=eb_norm,
            outcome_signal=r.get("outcome_signal", 0.0),
            confidence=r.get("extraction_confidence", 0.5),
            merge_count=r.get("merge_count", 0),
            days_since_created=days_old,
        )
        update_knowledge_quality(r["id"], quality)
        updated += 1

    if updated:
        logger.info(f"Recomputed quality scores for {updated} active records")
