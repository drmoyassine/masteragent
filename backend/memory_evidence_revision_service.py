"""Structured evidence-to-canonical revision using preview-like validation."""
from __future__ import annotations

import json
from typing import Any, Dict, Sequence

from core.storage import get_memory_db_context
from memory_evidence_repository import apply_canonical_revision, link_evidence_to_canonical

PROMPT_VERSION = "evidence-revision-v1"


async def assess_and_apply(
    *, route: Dict[str, Any], sources: Sequence[Dict[str, Any]], settings: Dict[str, Any],
) -> Dict[str, Any]:
    canonical_id = route.get("canonical_knowledge_id")
    if not canonical_id: return {"action": "create_new"}
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM knowledge WHERE id=%s AND status='active'", (canonical_id,))
        row = cur.fetchone()
    if not row: return {"action": "create_new"}
    canonical = dict(row)
    source_text = "\n\n---\n\n".join(
        f"SOURCE {s['source_type']}:{s['source_id']}\n{s.get('name','')}\n{s.get('summary','')}\n{s.get('content','')}"
        for s in sources
    )
    from memory_consolidation_prompts import build_system_prompt
    system = build_system_prompt(canonical.get("category")) + "\n\n" + (
        "Assess whether new source evidence changes an established canonical Knowledge record. "
        "Preserve all supported information and never invent. Return JSON only with decision "
        "no_change|revise|create_new|manual_review, confidence, rationale, contradictions, and "
        "canonical{name,summary,content,signals,tags,metadata} when decision=revise."
    )
    from memory_services import call_llm
    from services.llm import parse_llm_json
    raw = await call_llm(
        f"CANONICAL:\n{json.dumps({k:v for k,v in canonical.items() if k != 'embedding'},default=str)}\n\nNEW EVIDENCE:\n{source_text[:10000]}",
        system_prompt=system, max_tokens=int(settings.get("knowledge_generation_max_tokens",1200)),
        task_type="knowledge_consolidation",
    )
    proposal = parse_llm_json(raw, context="evidence_revision")
    decision = proposal.get("decision")
    if decision not in {"no_change","revise","create_new","manual_review"}:
        return {"action": "manual_review", "proposal": proposal, "error": "invalid_decision"}
    if decision == "no_change":
        event_id = link_evidence_to_canonical(
            bundle_id=route["bundle_id"], canonical_id=canonical_id, sources=sources,
            metrics=route["metrics"], settings={}, event_type="revision_no_change",
        )
        return {"action": "no_change", "event_id": event_id, "proposal": proposal}
    if decision != "revise":
        return {"action": decision, "proposal": proposal}
    approved = proposal.get("canonical") or {}
    if not str(approved.get("name") or "").strip() or not str(approved.get("content") or "").strip():
        return {"action": "manual_review", "proposal": proposal, "error": "invalid_canonical"}
    from memory_embedding import embed_knowledge_fields, current_embedding_model
    embedding, model = await embed_knowledge_fields(
        name=approved["name"], category=canonical.get("category"),
        content=approved["content"], summary=approved.get("summary", ""),
        signals=approved.get("signals") or [], tags=approved.get("tags") or [],
        metadata=approved.get("metadata") or {},
    )
    if not embedding: return {"action": "manual_review", "proposal": proposal, "error": "embedding_failed"}
    event_id = apply_canonical_revision(
        bundle_id=route["bundle_id"], canonical_id=canonical_id,
        expected_version=int(canonical.get("version") or 1), approved=approved,
        embedding=embedding, embedding_model=model or current_embedding_model(),
        sources=sources, metrics=route["metrics"], proposal=proposal,
    )
    return {"action": "revised", "event_id": event_id, "proposal": proposal}
