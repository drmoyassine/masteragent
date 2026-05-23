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
