"""Versioned, explainable Knowledge quality model (v2)."""
from __future__ import annotations

import math
from typing import Any, Dict

from core.storage import get_memory_db_context

QUALITY_VERSION = 2


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def calculate_quality_v2(
    *, unique_bundle_count: int, diversity_count: int, success_count: int,
    failure_count: int, generation_confidence: float,
    provenance_completeness: float, approval_assurance: float,
) -> Dict[str, Any]:
    volume = min(math.log1p(max(0, unique_bundle_count)) / math.log1p(10), 1.0)
    diversity = min(max(0, diversity_count) / 5.0, 1.0)
    evidence = _clamp(0.6 * volume + 0.4 * diversity)
    outcome = _clamp((max(0, success_count) + 2) / (max(0, success_count) + max(0, failure_count) + 4))
    confidence = _clamp(generation_confidence)
    validation = _clamp(0.75 * provenance_completeness + 0.25 * approval_assurance)
    score = _clamp(0.35 * evidence + 0.30 * outcome + 0.20 * confidence + 0.15 * validation)
    return {
        "version": QUALITY_VERSION,
        "score": round(score, 6),
        "components": {
            "evidence_strength": round(evidence, 6),
            "outcome_feedback": round(outcome, 6),
            "generation_confidence": round(confidence, 6),
            "validation_provenance": round(validation, 6),
        },
        "inputs": {
            "unique_bundle_count": unique_bundle_count,
            "diversity_count": diversity_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "provenance_completeness": round(_clamp(provenance_completeness), 6),
            "approval_assurance": round(_clamp(approval_assurance), 6),
        },
    }


def recalculate_knowledge_quality(knowledge_id: str) -> Dict[str, Any] | None:
    import json
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id,status,approval_origin,extraction_confidence,success_count,failure_count,
                   embedding,embedding_model,facet_status,source_pathway
            FROM knowledge WHERE id=%s
        """, (knowledge_id,))
        row = cur.fetchone()
        if not row: return None
        cur.execute("""
            SELECT COUNT(DISTINCT COALESCE(bundle_id, source_type || ':' || source_id)) AS bundles,
                   COUNT(DISTINCT COALESCE(i.primary_entity_id, x.primary_entity_id, source_id)) AS diversity,
                   COUNT(*) AS links
            FROM knowledge_source_links l
            LEFT JOIN intelligence i ON l.source_type='intelligence' AND i.id=l.source_id
            LEFT JOIN interactions x ON l.source_type='interaction' AND x.id=l.source_id
            WHERE l.knowledge_id=%s
        """, (knowledge_id,))
        evidence = cur.fetchone() or {}
        links = int(evidence.get("links") or 0)
        provenance_parts = [bool(row.get("source_pathway")), links > 0 or row.get("source_pathway") in ("manual", "import", "system"),
                            row.get("embedding") is not None and bool(row.get("embedding_model")),
                            row.get("facet_status") in ("succeeded", "no_facet", "explicit")]
        provenance = sum(1 for part in provenance_parts if part) / len(provenance_parts)
        approval_origin = row.get("approval_origin")
        assurance = 1.0 if approval_origin == "manual" else 0.7 if row["status"] == "active" else 0.0
        result = calculate_quality_v2(
            unique_bundle_count=int(evidence.get("bundles") or (1 if links else 0)),
            diversity_count=int(evidence.get("diversity") or 0),
            success_count=int(row.get("success_count") or 0),
            failure_count=int(row.get("failure_count") or 0),
            generation_confidence=float(row.get("extraction_confidence") if row.get("extraction_confidence") is not None else 0.5),
            provenance_completeness=provenance, approval_assurance=assurance,
        )
        # Explicit human approval of a manually curated record is the strongest
        # available assurance for that record. Keep the component breakdown for
        # explanation, but expose the approved manual record as fully trusted.
        if row.get("status") == "active" and approval_origin == "manual":
            result["score"] = 1.0
            result["score_basis"] = "human_approved_manual"
        cur.execute("""
            UPDATE knowledge SET quality_score=%s,quality_version=%s,
                quality_components=%s::jsonb,outcome_signal=%s,updated_at=NOW()
            WHERE id=%s
        """, (result["score"], QUALITY_VERSION, json.dumps(result),
              result["components"]["outcome_feedback"], knowledge_id))
    return result


def backfill_quality_v2(limit: int = 1000) -> Dict[str, int]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id FROM knowledge
                       WHERE COALESCE(quality_version,0)<>%s
                          OR (status='active' AND approval_origin='manual' AND COALESCE(quality_score,0)<>1.0)
                       ORDER BY created_at LIMIT %s""",
                    (QUALITY_VERSION, limit))
        ids = [r["id"] for r in cur.fetchall()]
    updated = sum(1 for kid in ids if recalculate_knowledge_quality(kid))
    return {"processed": len(ids), "updated": updated}
