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
from typing import Optional

from core.storage import get_memory_db_context
from memory_services import get_memory_settings
from services.llm import parse_llm_json
from memory_helpers import _get_entity_type_config

logger = logging.getLogger(__name__)


async def run_consolidation(*, max_records: int = 1000, max_clusters: int = 100,
                            progress_run_id: Optional[str] = None):
    """Run hygiene + decay + quality maintenance.

    The destructive pairwise retirement loop is GONE. Candidate discovery and
    consolidation proposals now go through the shared hygiene service
    (``memory_consolidation_service.discover_and_propose``), which respects the
    configured mode and never applies unless policy gates pass. Decay and
    quality-score recompute remain as non-destructive maintenance.
    """
    settings = get_memory_settings()
    logger.info("Starting consolidation run (hygiene mode)")

    # Knowledge hygiene discovery + proposals (mode-gated; manual_only never applies).
    hygiene_error = None
    if settings.get("knowledge_hygiene_enabled", True):
        try:
            from memory_consolidation_service import discover_and_propose
            mode = settings.get("knowledge_hygiene_mode", "manual_only")
            await discover_and_propose(
                origin="scheduled", mode=mode,
                auto_apply=mode in ("auto_conservative", "auto_synthesis"),
                max_records=max_records, max_clusters=max_clusters,
                progress_run_id=progress_run_id,
            )
        except Exception as exc:
            hygiene_error = exc
            logger.exception("Hygiene discovery failed during consolidation run")

    _apply_decay()
    _recompute_quality_scores()
    if hygiene_error is not None:
        # Let the queue retry/DLQ policy observe the failure instead of silently
        # reporting a successful scheduled run. Maintenance above remains safe
        # and idempotent if the job is retried.
        raise hygiene_error
    logger.info("Consolidation run complete")


# Legacy pairwise retirement removed — see run_consolidation above. The shared
# hygiene service is the single consolidation path (preview + transactional apply).
async def _consolidate_duplicates(threshold: float):  # pragma: no cover - legacy shim
    """Deprecated: retained only as a no-op shim for any stale callers."""
    logger.warning("_consolidate_duplicates is deprecated; hygiene service handles consolidation")
    return


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
    """Batch recompute every record with the canonical explainable v2 model."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM knowledge")
        total = int(cursor.fetchone()["n"] or 0)
    from memory_quality import backfill_quality_v2
    updated = 0
    while updated < total:
        result = backfill_quality_v2(limit=500)
        updated += result["updated"]
        if result["processed"] == 0 or result["updated"] == 0:
            break

    if updated:
        logger.info(f"Recomputed quality scores for {updated} active records")
