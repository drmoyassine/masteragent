"""Deduplication, merge tracking, and quality scoring for unified knowledge table."""
import logging
from datetime import datetime, timezone
from typing import Optional

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


async def find_similar_existing(
    embedding: list,
    threshold: float,
    category: str = None,
) -> Optional[str]:
    """Find an existing knowledge record with cosine similarity above threshold.

    Returns the matching record's ID, or None if no match found.
    Optionally scope to a specific category.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        category_clause = "AND category = %s" if category else ""
        params = [embedding, threshold]
        if category:
            params.append(category)

        cursor.execute(f"""
            SELECT id FROM knowledge
            WHERE 1 - (embedding <=> %s::vector) > %s
              AND status != 'retired'
              {category_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT 1
        """, params + [embedding])
        row = cursor.fetchone()
        return row["id"] if row else None


def increment_merge(existing_id: str) -> None:
    """Increment merge_count and set last_merged_at for an existing record."""
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE knowledge
            SET merge_count = merge_count + 1,
                last_merged_at = %s,
                updated_at = %s
            WHERE id = %s
        """, (now, now, existing_id))


_REFINE_PROMPT = (
    "You are maintaining a single, canonical piece of organizational knowledge. "
    "You are given the ESTABLISHED record and a NEW corroborating observation that was "
    "found to be about the same thing.\n\n"
    "Your job is preservation-first consolidation:\n"
    "- Keep the established record's structure, voice, and every fact it already contains.\n"
    "- Integrate ONLY genuinely new, non-redundant detail from the new observation.\n"
    "- If the new observation adds nothing, return the established content UNCHANGED.\n"
    "- Never shorten or weaken the record; never invent facts; stay concise.\n\n"
    "Return JSON only: {\"content\": \"<the updated record body>\", \"summary\": \"<1-2 sentence description: what it is and when it applies>\"}"
)


async def refine_or_increment_merge(
    existing_id: str,
    *,
    new_name: str = "",
    new_content: str = "",
    new_summary: str = "",
) -> str:
    """When a new precursor matches an existing knowledge record, merge the new
    evidence into it (update-in-place) rather than only counting the match.

    Conservative and safe: gated by the knowledge_refine_on_merge setting, and on
    ANY failure it falls back to a plain merge-count increment — so this can never
    regress an existing record. Returns 'refined' or 'incremented'.
    """
    import json as _json
    from memory_services import call_llm, generate_embedding, get_memory_settings
    from services.llm import parse_llm_json
    from memory_skill_md import SKILL_MD_CATEGORIES, is_skill_md, parse_skill_md, render_skill_md
    from datetime import datetime, timezone

    settings = get_memory_settings() or {}
    if not settings.get("knowledge_refine_on_merge", True):
        increment_merge(existing_id)
        return "incremented"

    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, category, content, summary, metadata, signals, tags, version
                FROM knowledge WHERE id = %s
            """, (existing_id,))
            row = cursor.fetchone()
        if not row:
            increment_merge(existing_id)
            return "incremented"
        row = dict(row)
        category = row.get("category") or "trade_knowledge"

        # Extract the human-meaningful body to refine (skill/playbook content is
        # SKILL.md; feed only its body to the LLM, then re-render).
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = _json.loads(metadata)
        existing_body = row.get("content") or ""
        existing_desc = row.get("summary") or ""
        if category in SKILL_MD_CATEGORIES and is_skill_md(existing_body):
            try:
                parsed = parse_skill_md(existing_body)
                existing_desc = existing_desc or parsed["description"]
                existing_body = parsed["body"]
            except ValueError:
                pass

        user_msg = (
            f"--- ESTABLISHED RECORD ---\n{existing_desc}\n\n{existing_body}\n\n"
            f"--- NEW OBSERVATION ---\n{new_name}\n{new_summary}\n{new_content}"
        )
        result_text = await call_llm(
            user_msg[:8000],
            system_prompt=_REFINE_PROMPT,
            max_tokens=settings.get("knowledge_max_tokens") or 1200,
            task_type="knowledge_generation",
        )
        result = parse_llm_json(result_text, context="knowledge_refine")
        refined_content = (result.get("content") or "").strip()
        refined_summary = (result.get("summary") or existing_desc).strip()
        if not refined_content:
            increment_merge(existing_id)
            return "incremented"

        new_version = (row.get("version") or 1) + 1
        # Re-render skill/playbook back into SKILL.md; declarative stays plain text.
        stored_content = refined_content
        if category in SKILL_MD_CATEGORIES:
            stored_content = render_skill_md(
                name=row.get("name", ""),
                category=category,
                description=refined_summary,
                body=refined_content,
                metadata=metadata,
                signals=row.get("signals") or [],
                tags=row.get("tags") or [],
                version=new_version,
            )

        embedding = None
        try:
            from memory_embedding import embed_knowledge_fields
            embedding, _model = await embed_knowledge_fields(
                name=row.get("name", ""), category=category,
                content=refined_content, summary=refined_summary,
                signals=row.get("signals") or [], tags=row.get("tags") or [],
                metadata=metadata,
            )
        except Exception:
            pass

        now = datetime.now(timezone.utc).isoformat()
        # Stamp embedding provenance onto metadata so the refined record stays
        # version-compatible for candidate discovery.
        stamped_metadata = metadata
        if embedding is not None:
            try:
                from memory_embedding import merge_embedding_metadata
                stamped_metadata = merge_embedding_metadata(
                    metadata or {}, model=_model, vector=embedding
                )
            except Exception:
                stamped_metadata = metadata
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            if embedding is not None:
                cursor.execute("""
                    UPDATE knowledge
                    SET content = %s, summary = %s, embedding = %s, metadata = %s,
                        version = %s, merge_count = merge_count + 1,
                        last_merged_at = %s, updated_at = %s
                    WHERE id = %s
                """, (stored_content, refined_summary, embedding, _json.dumps(stamped_metadata),
                      new_version, now, now, existing_id))
            else:
                cursor.execute("""
                    UPDATE knowledge
                    SET content = %s, summary = %s,
                        version = %s, merge_count = merge_count + 1,
                        last_merged_at = %s, updated_at = %s
                    WHERE id = %s
                """, (stored_content, refined_summary, new_version, now, now, existing_id))
        logger.info(f"Refined knowledge {existing_id} on merge (v{new_version})")
        return "refined"
    except Exception as e:
        logger.warning(f"refine_on_merge failed for {existing_id}, falling back to increment: {e}")
        increment_merge(existing_id)
        return "incremented"


def compute_quality_score(
    evidence_breadth_norm: float,
    outcome_signal: float,
    confidence: float,
    merge_count: int,
    days_since_created: float = 0.0,
) -> float:
    """Compute a 0-1 quality score for a knowledge record.

    Weights:
      evidence_breadth  25% — how many distinct entities contributed
      outcome_signal    30% — success rate from feedback
      confidence        15% — LLM extraction confidence
      merge_count       20% — recurrence signal (capped at 10 merges)
      recency           10% — decays over 365 days
    """
    recency = max(0.0, 1.0 - days_since_created / 365.0)
    return (
        evidence_breadth_norm * 0.25
        + outcome_signal * 0.30
        + confidence * 0.15
        + min(merge_count / 10.0, 1.0) * 0.20
        + recency * 0.10
    )
