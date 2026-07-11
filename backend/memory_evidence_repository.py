"""Database persistence for pre-generation evidence routing."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from core.storage import get_memory_db_context


def source_digest(pathway: str, sources: Sequence[Dict[str, Any]]) -> str:
    refs = sorted(
        f"{s.get('source_type')}:{s.get('source_id')}:{s.get('source_role', 'primary')}"
        for s in sources
    )
    return hashlib.sha256((pathway + "\n" + "\n".join(refs)).encode("utf-8")).hexdigest()


def upsert_bundle(
    *, pathway: str, sources: Sequence[Dict[str, Any]], aggregate_embedding: Sequence[float],
    embedding_model: str, embedding_version: int, entity_type: str | None,
    entity_ids: Sequence[str], context_digest: str | None = None,
    outcome_signature: Dict[str, Any] | None = None,
) -> str:
    digest = source_digest(pathway, sources)
    bundle_id = str(uuid.uuid4())
    dims = len(aggregate_embedding)
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO knowledge_evidence_bundles(
                id, pathway, source_types, source_digest, entity_type, entity_ids,
                aggregate_embedding, embedding_model, embedding_version,
                embedding_dimensions, context_digest, outcome_signature
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::vector,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(pathway, source_digest) DO UPDATE SET updated_at=NOW()
            RETURNING id
        """, (
            bundle_id, pathway, sorted({s["source_type"] for s in sources}), digest,
            entity_type, list(dict.fromkeys(entity_ids)), list(aggregate_embedding),
            embedding_model, embedding_version, dims, context_digest,
            json.dumps(outcome_signature or {}),
        ))
        bundle_id = cur.fetchone()["id"]
        for ordinal, source in enumerate(sources):
            cur.execute("""
                INSERT INTO knowledge_evidence_bundle_members(
                    bundle_id, source_type, source_id, source_role, ordinal,
                    entity_type, entity_id, source_timestamp, embedding_model,
                    embedding_version, embedding_dimensions
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (
                bundle_id, source["source_type"], source["source_id"],
                source.get("source_role", "primary"), ordinal,
                source.get("entity_type"), source.get("entity_id"),
                source.get("timestamp"), source.get("embedding_model"),
                source.get("embedding_version"), len(source.get("embedding") or []),
            ))
    return bundle_id


def load_linked_historical_sources(source_type: str, exclude_ids: Sequence[str],
                                   categories: Sequence[str] | None = None) -> List[Dict[str, Any]]:
    table = "intelligence" if source_type == "intelligence" else "interactions"
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT DISTINCT s.id, s.embedding, s.embedding_model, s.embedding_version,
                   s.embedding_dimensions, l.knowledge_id,
                   k.status AS knowledge_status, k.merged_into
            FROM {table} s
            JOIN knowledge_source_links l
              ON l.source_type = %s AND l.source_id = s.id
            JOIN knowledge k ON k.id = l.knowledge_id
            WHERE s.embedding IS NOT NULL
              AND NOT (s.id = ANY(%s))
              AND k.status IN ('active','retired')
              AND (%s::text[] IS NULL OR k.category = ANY(%s::text[]))
            ORDER BY s.id
            LIMIT 5000
        """, (source_type, list(exclude_ids) or ["__none__"],
              list(categories) if categories else None,
              list(categories) if categories else None))
        return [dict(r) for r in cur.fetchall()]


def resolve_active_canonical(knowledge_id: str) -> str | None:
    current = knowledge_id
    seen = set()
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        while current and current not in seen:
            seen.add(current)
            cur.execute("SELECT id, status, merged_into FROM knowledge WHERE id=%s", (current,))
            row = cur.fetchone()
            if not row:
                return None
            if row["status"] == "active":
                return row["id"]
            current = row.get("merged_into")
    return None


def update_bundle_analysis(bundle_id: str, analysis: Dict[str, Any]) -> None:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE knowledge_evidence_bundles
            SET status='analyzed', route=%s, route_metrics=%s::jsonb,
                matched_bundle_ids=%s, matched_knowledge_ids=%s,
                canonical_knowledge_id=%s, updated_at=NOW()
            WHERE id=%s
        """, (
            analysis["route"], json.dumps(analysis["metrics"]),
            analysis.get("matched_bundle_ids") or [],
            analysis.get("matched_knowledge_ids") or [],
            analysis.get("canonical_knowledge_id"), bundle_id,
        ))


def link_evidence_to_canonical(
    *, bundle_id: str, canonical_id: str, sources: Sequence[Dict[str, Any]],
    metrics: Dict[str, Any], settings: Dict[str, Any], event_type: str = "generation_skipped_evidence_linked",
) -> str:
    """Atomically link corroborating evidence without rewriting canonical content."""
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"evidence:{canonical_id}",))
        cur.execute("SELECT id, status FROM knowledge WHERE id=%s FOR UPDATE", (canonical_id,))
        row = cur.fetchone()
        if not row or row["status"] != "active":
            raise RuntimeError("Canonical is no longer active")
        intel_ids, interaction_ids = [], []
        for source in sources:
            st, sid = source["source_type"], source["source_id"]
            cur.execute("""
                INSERT INTO knowledge_source_links(
                    knowledge_id, source_type, source_id, bundle_id, source_role,
                    linked_by_event_id
                ) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
            """, (canonical_id, st, sid, bundle_id, source.get("source_role", "primary"), event_id))
            if st == "intelligence": intel_ids.append(sid)
            if st == "interaction": interaction_ids.append(sid)
        cur.execute("""
            UPDATE knowledge SET
                source_intelligence_ids=(SELECT ARRAY(SELECT DISTINCT unnest(source_intelligence_ids || %s::text[]))),
                source_ai_interaction_ids=(SELECT ARRAY(SELECT DISTINCT unnest(source_ai_interaction_ids || %s::text[]))),
                evidence_breadth=(SELECT COUNT(DISTINCT bundle_id) FROM knowledge_source_links WHERE knowledge_id=%s AND bundle_id IS NOT NULL),
                updated_at=%s
            WHERE id=%s
        """, (intel_ids, interaction_ids, canonical_id, now, canonical_id))
        cur.execute("""
            INSERT INTO knowledge_evidence_events(
                id,bundle_id,knowledge_id,event_type,actor_type,origin,
                similarity_settings,route_metrics,source_ids
            ) VALUES (%s,%s,%s,%s,'system','generation_policy',%s::jsonb,%s::jsonb,%s)
        """, (event_id, bundle_id, canonical_id, event_type, json.dumps(settings), json.dumps(metrics),
              [s["source_id"] for s in sources]))
        cur.execute("UPDATE knowledge_evidence_bundles SET status='linked', canonical_knowledge_id=%s, updated_at=NOW() WHERE id=%s",
                    (canonical_id, bundle_id))
    return event_id


def apply_canonical_revision(
    *, bundle_id: str, canonical_id: str, expected_version: int,
    approved: Dict[str, Any], embedding: Sequence[float], embedding_model: str,
    sources: Sequence[Dict[str, Any]], metrics: Dict[str, Any], proposal: Dict[str, Any],
) -> str:
    event_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"evidence:{canonical_id}",))
        cur.execute("SELECT * FROM knowledge WHERE id=%s FOR UPDATE", (canonical_id,))
        row = cur.fetchone()
        if not row or row["status"] != "active" or int(row.get("version") or 1) != expected_version:
            raise RuntimeError("Canonical changed after evidence-revision preview")
        previous = dict(row)
        stored_content = approved["content"]
        if row.get("category") in ("skill", "playbook"):
            from memory_skill_md import is_skill_md, render_skill_md
            if not is_skill_md(stored_content):
                stored_content = render_skill_md(
                    name=approved["name"], category=row["category"],
                    description=approved.get("summary") or stored_content,
                    body=stored_content, metadata=approved.get("metadata") or {},
                    signals=approved.get("signals") or [], tags=approved.get("tags") or [],
                    version=expected_version + 1,
                )
        cur.execute("""
            UPDATE knowledge SET name=%s,summary=%s,content=%s,signals=%s,tags=%s,
                metadata=%s::jsonb,embedding=%s::vector,embedding_model=%s,
                embedding_version=%s,embedding_dimensions=%s,embedded_at=NOW(),
                version=version+1,updated_at=NOW()
            WHERE id=%s
        """, (
            approved["name"], approved.get("summary", ""), stored_content,
            approved.get("signals") or [], approved.get("tags") or [],
            json.dumps(approved.get("metadata") or {}), list(embedding), embedding_model,
            2, len(embedding), canonical_id,
        ))
        for source in sources:
            cur.execute("""
                INSERT INTO knowledge_source_links(
                    knowledge_id,source_type,source_id,bundle_id,source_role,linked_by_event_id
                ) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
            """, (canonical_id, source["source_type"], source["source_id"], bundle_id,
                  source.get("source_role", "primary"), event_id))
        cur.execute("""
            INSERT INTO knowledge_evidence_events(
                id,bundle_id,knowledge_id,event_type,actor_type,origin,route_metrics,
                source_ids,previous_snapshot,approved_output,prompt_version
            ) VALUES (%s,%s,%s,'revision_applied','system','generation_policy',%s::jsonb,%s,%s::jsonb,%s::jsonb,'evidence-revision-v1')
        """, (event_id,bundle_id,canonical_id,json.dumps(metrics),
              [s["source_id"] for s in sources],json.dumps(previous,default=str),
              json.dumps({"proposal": proposal, "approved": approved})))
        cur.execute("UPDATE knowledge_evidence_bundles SET status='revised',canonical_knowledge_id=%s,updated_at=NOW() WHERE id=%s",
                    (canonical_id,bundle_id))
    from memory_quality import recalculate_knowledge_quality
    recalculate_knowledge_quality(canonical_id)
    return event_id
