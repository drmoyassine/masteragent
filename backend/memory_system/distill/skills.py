"""Skill extraction from intelligence clusters + AI telemetry.

Runs on a weekly cadence (or evidence-threshold override). Clusters confirmed
intelligence by cosine similarity across distinct entities, enriches clusters
with AI thoughts/tool calls from the same time window, then extracts skills
directly into the unified knowledge table.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from core.storage import get_memory_db_context
from services import call_llm, get_memory_settings
from memory_system.maintain.similarity import connected_components
from services.llm import parse_llm_json
from services.prompt_safety import (
    emit_safety_alert,
    frame_untrusted,
    record_injection_flag,
    resolve_creation_status,
    scan_untrusted_output,
)
from memory_system.store.writes import insert_knowledge
from memory_system.store.helpers import _get_entity_type_config
from memory_system.distill.policy import approval_status, resolve_generation_policy
from memory_system.distill.facets import facet_prompt_instructions, validate_generated_facets

logger = logging.getLogger(__name__)


# Canonical prompt — seeded into the memory_llm_configs node (pipeline_stage='knowledge')
# so it is admin-editable. The generation function reads the node prompt via
# get_task_system_prompt() and falls back to this constant if no node/empty prompt.
_SKILL_GEN_PROMPT = (
    "You are a skill extractor for an agent harness.\n\n"
    "You are given a cluster of intelligence signals that were independently observed "
    "across {entity_count} different {entity_type} entities, along with AI agent telemetry "
    "from the interactions where these signals appeared.\n\n"
    "Identify 1-3 distinct reusable capabilities (skills) supported by the cluster. Each "
    "skill should be a discrete, composable ability grounded in the observed evidence. "
    "Return no output when no reusable capability is supported. Do not invent steps, tools, "
    "permissions, or outcomes; preserve qualifications and surface uncertainty rather than "
    "forcing a capability.\n\n"
    "A skill is an operational contract, not a label. Do not name a tool, permission, or "
    "environment unless the source supports it; naming one never grants it.\n\n"
    "Return ONLY a JSON array. Each object has schema_version='knowledge-generation-v2', name, "
    "skill_type, summary, purpose, trigger_desc, procedure, inputs, outputs, tools, prerequisites, "
    "permissions, environments, agent_types, side_effects, failure_conditions, recovery, "
    "safety_requirements, examples, edge_cases, signals, tags, facets, qualifications, "
    "contradictions, source_support, confidence. trigger_desc must state both what the skill does "
    "and concrete contexts/keywords for when to use it."
)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_skill_check():
    """Check for skill extraction opportunities across all entity types."""
    settings = get_memory_settings()
    policy = resolve_generation_policy("skill_extraction", settings=settings)["values"]
    if not policy["enabled"]:
        return 0
    threshold = settings.get("dedup_similarity_threshold", 0.85)
    confidence_min = policy["min_confidence"]

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        # Find entity types with unlinked confirmed intelligence
        cursor.execute("""
            SELECT primary_entity_type, COUNT(*) as cnt
            FROM intelligence i
            WHERE i.status = 'confirmed'
              AND i.embedding IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM knowledge k
                  WHERE k.category = 'skill'
                    AND i.id = ANY(k.source_intelligence_ids)
              )
            GROUP BY primary_entity_type
        """)
        entity_types = [dict(r) for r in cursor.fetchall()]

    for row in entity_types:
        entity_type = row["primary_entity_type"]
        count = row["cnt"]
        config = _get_entity_type_config(entity_type)
        min_entities = config.get("extraction_min_entities", 3)

        if count < min_entities:
            logger.info(f"Skill extraction: {entity_type} has {count} unlinked intelligence (need {min_entities})")
            continue

        logger.info(f"Skill extraction: processing {entity_type} ({count} unlinked intelligence)")
        try:
            await _process_entity_type(entity_type, threshold, confidence_min, min_entities, config)
        except Exception as e:
            logger.error(f"Skill extraction failed for {entity_type}: {e}")


async def _process_entity_type(
    entity_type: str,
    dedup_threshold: float,
    confidence_min: float,
    min_entities: int,
    config: dict,
):
    """Cluster intelligence, enrich with AI telemetry, extract skills directly."""

    # 1. Find pairwise similar intelligence across DISTINCT entities
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id AS aid, b.id AS bid,
                   a.primary_entity_id AS a_entity, b.primary_entity_id AS b_entity,
                   1 - (a.embedding <=> b.embedding) AS similarity
            FROM intelligence a
            JOIN intelligence b ON a.id < b.id
              AND a.primary_entity_type = b.primary_entity_type
              AND a.primary_entity_id != b.primary_entity_id
              AND a.status = 'confirmed' AND b.status = 'confirmed'
              AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
            WHERE a.primary_entity_type = %s
              AND 1 - (a.embedding <=> b.embedding) > %s
              AND NOT EXISTS (
                  SELECT 1 FROM knowledge k
                  WHERE k.category = 'skill'
                    AND a.id = ANY(k.source_intelligence_ids)
              )
            ORDER BY similarity DESC
            LIMIT 200
        """, (entity_type, dedup_threshold))
        pairs = [dict(r) for r in cursor.fetchall()]

    if not pairs:
        logger.info(f"No similar intelligence pairs found for {entity_type}")
        return

    # 2. Cluster similar pairs via the shared union-find (memory_system.maintain.similarity)
    all_ids = {p["aid"] for p in pairs} | {p["bid"] for p in pairs}
    edges = [(p["aid"], p["bid"], 0.0) for p in pairs]
    components = connected_components(all_ids, edges)

    # 3. Filter: cluster must span >= min_entities distinct entities
    qualifying = []
    for component in components:
        ids = list(component)
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT primary_entity_id FROM intelligence
                WHERE id = ANY(%s)
            """, (ids,))
            entity_ids = [r["primary_entity_id"] for r in cursor.fetchall()]
        if len(entity_ids) >= min_entities:
            qualifying.append((ids, entity_ids))

    logger.info(f"Found {len(qualifying)} qualifying clusters for {entity_type}")

    # 4. Process each qualifying cluster
    for intel_ids, entity_ids in qualifying:
        await _process_cluster(entity_type, intel_ids, entity_ids, confidence_min, config)


async def _process_cluster(
    entity_type: str,
    intel_ids: list,
    entity_ids: list,
    confidence_min: float,
    config: dict,
):
    """Enrich cluster with AI telemetry, extract skills directly."""

    # Fetch the intelligence records
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, content, summary, signals, created_at, embedding,
                   primary_entity_id, embedding_model, embedding_version,
                   embedding_dimensions, embedded_at
            FROM intelligence WHERE id = ANY(%s)
        """, (intel_ids,))
        intel_records = [dict(r) for r in cursor.fetchall()]

    # Fetch AI thoughts + tool calls for the same entities in the same time window.
    # created_at is TIMESTAMPTZ — psycopg returns datetime objects, but tolerate
    # ISO strings too (e.g. test fixtures).
    def _as_dt(v):
        return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))

    min_ts = min(_as_dt(r["created_at"]) for r in intel_records)
    max_ts = max(_as_dt(r["created_at"]) for r in intel_records)
    # Widen window by 1 hour on each side
    window_start = (min_ts - timedelta(hours=1)).isoformat()
    window_end = (max_ts + timedelta(hours=1)).isoformat()

    ai_interactions = []
    processed_ids = []
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, interaction_type, primary_entity_id, timestamp,
                   embedding, embedding_model, embedding_version,
                   embedding_dimensions, embedded_at
            FROM interactions
            WHERE interaction_type IN ('internal_ai_thought', 'internal_ai_tool_call')
              AND primary_entity_type = %s
              AND primary_entity_id = ANY(%s)
              AND timestamp BETWEEN %s AND %s
              AND NOT EXISTS (
                  SELECT 1 FROM skill_processed_interactions p WHERE p.interaction_id = interactions.id
              )
            ORDER BY timestamp
            LIMIT 100
        """, (entity_type, entity_ids, window_start, window_end))
        ai_interactions = [dict(r) for r in cursor.fetchall()]
        processed_ids = [r["id"] for r in ai_interactions]

    # Build context for LLM
    intel_context = "\n\n".join(
        f"[{', '.join(r.get('signals') or []) or 'signal'}] {r.get('name', '')}\n{r.get('content', '')}"
        for r in intel_records
    )
    ai_context = ""
    if ai_interactions:
        ai_context = "\n\n--- AI Agent Telemetry ---\n" + "\n\n".join(
            f"[{r['interaction_type']}] Entity: {r['primary_entity_id']}\n{r.get('content', '')[:500]}"
            for r in ai_interactions
        )

    # Compute centroid embedding for deterministic serialization and routing.
    embeddings = [r["embedding"] for r in intel_records if r.get("embedding")]
    if not embeddings:
        return
    centroid = [sum(vals) / len(vals) for vals in zip(*embeddings)]

    settings = get_memory_settings() or {}
    policy = resolve_generation_policy(
        "skill_extraction", settings=settings, entity_config=config,
    )["values"]
    sources = [{
        "source_type": "intelligence", "source_id": str(r["id"]),
        "entity_id": r.get("primary_entity_id"), "name": r.get("name") or "",
        "summary": r.get("summary") or "", "content": r.get("content") or "",
        "embedding": r.get("embedding"), "embedding_model": r.get("embedding_model"),
        "embedding_version": r.get("embedding_version"),
        "embedding_dimensions": r.get("embedding_dimensions"), "embedded_at": r.get("embedded_at"),
    } for r in intel_records] + [{
        "source_type": "interaction", "source_id": str(r["id"]),
        "entity_id": r.get("primary_entity_id"), "name": r.get("interaction_type") or "",
        "summary": "", "content": r.get("content") or "",
        "embedding": r.get("embedding"), "embedding_model": r.get("embedding_model"),
        "embedding_version": r.get("embedding_version"),
        "embedding_dimensions": r.get("embedding_dimensions"), "embedded_at": r.get("embedded_at"),
    } for r in ai_interactions]
    try:
        from memory_system.distill.evidence_service import route_evidence_or_link
        routing = await route_evidence_or_link(
            pathway="skill_extraction", sources=sources, settings=settings,
            entity_type=entity_type,
        )
        if routing["linked_id"] or routing["revision_action"] in {"no_change", "revised"}:
            _mark_processed(processed_ids)
            return
        if routing["revision_action"] == "manual_review":
            return
    except Exception as exc:
        logger.exception("Skill evidence routing failed: %s", exc)

    # Domain signals inherited from the union of the source intelligence signals.
    cluster_signals = list(dict.fromkeys(
        s for r in intel_records for s in (r.get("signals") or [])
    ))

    # Generate skills via LLM
    skills = await _generate_skills(
        entity_type, intel_context, ai_context, len(entity_ids), policy,
    )
    if not skills:
        _mark_processed(processed_ids)
        return

    for skill_data in skills[:5]:
        try:
            from memory_system.distill.contracts import validate_skill
            skill_data = validate_skill(skill_data).model_dump()
        except ValueError as exc:
            logger.warning("Rejected invalid skill output: %s", exc)
            continue
        confidence = float(skill_data.get("confidence") or 0.0)
        if confidence < confidence_min:
            logger.info(f"Skill confidence {confidence} below threshold {confidence_min} — skipping")
            continue
        await _insert_skill(
            skill_data, confidence, policy, entity_type,
            entity_ids, intel_ids, cluster_signals, centroid, processed_ids, sources,
        )

    # Mark AI interactions as processed
    _mark_processed(processed_ids)


async def _insert_skill(
    skill_data: dict,
    confidence: float,
    policy: dict,
    entity_type: str,
    entity_ids: list,
    intel_ids: list,
    cluster_signals: list,
    centroid: list,
    processed_ids: list,
    sources: list,
):
    """Persist one extracted skill with the full safety doctrine applied."""
    skill_id = str(uuid.uuid4())
    sk_name = skill_data.get("name", "Unnamed Skill")
    sk_proc = skill_data.get("procedure", "")
    sk_trigger = skill_data.get("trigger_desc", "")
    metadata = {
        "entity_type": entity_type,
        "entity_types": entity_ids,
        "skill_type": skill_data.get("skill_type", "hard"),
        "trigger_desc": sk_trigger,
        "procedure": sk_proc,
        "purpose": skill_data.get("purpose", ""),
        "inputs": skill_data.get("inputs", []),
        "outputs": skill_data.get("outputs", []),
        "tools": skill_data.get("tools", []),
        "prerequisites": skill_data.get("prerequisites", []),
        "permissions": skill_data.get("permissions", []),
        "environments": skill_data.get("environments", []),
        "agent_types": skill_data.get("agent_types", []),
        "side_effects": skill_data.get("side_effects", []),
        "failure_conditions": skill_data.get("failure_conditions", []),
        "recovery": skill_data.get("recovery", []),
        "safety_requirements": skill_data.get("safety_requirements", []),
        "examples": skill_data.get("examples", []),
        "edge_cases": skill_data.get("edge_cases", []),
        "qualifications": skill_data.get("qualifications", []),
        "contradictions": skill_data.get("contradictions", []),
        "source_support": skill_data.get("source_support", []),
    }
    facets, facet_state = validate_generated_facets(skill_data.get("facets") or {})
    metadata["facets"] = facets
    metadata["facet_extraction"] = facet_state
    # Canonical category-aware embedding (covers skill operational fields).
    embedding = None
    try:
        from memory_system.maintain.embedding import embed_knowledge_fields
        embedding, _model = await embed_knowledge_fields(
            name=sk_name, category="skill", content=sk_proc,
            summary=sk_trigger, signals=cluster_signals,
            tags=skill_data.get("tags", []), metadata=metadata,
        )
    except Exception:
        pass

    # TASK-262: skills are behavior-changing artifacts derived from
    # externally-authored content — forced to draft when the policy would
    # have auto-activated them (DEC-091 posture), with a human-visible alert.
    status, ai_safety = resolve_creation_status(
        "experiential", "skill", approval_status(policy["approval_policy"]),
    )
    metadata["ai_safety"] = ai_safety
    # No-instructions invariant: flag directive-shaped text in the artifact we
    # are about to persist (flag-only — content is kept for human review).
    record_injection_flag(
        metadata,
        where="skill_extraction/skill_generation",
        matches=scan_untrusted_output(json.dumps(skill_data, default=str)),
        sample=str(sk_proc),
    )
    if ai_safety.get("forced_draft_reason"):
        try:
            with get_memory_db_context() as conn:
                emit_safety_alert(
                    conn.cursor(),
                    code="skill_forced_draft",
                    title="Skill held as draft (externally-derived content)",
                    message=(
                        f"Skill '{sk_name}' was generated from externally-derived "
                        "content and held as draft pending human activation."
                    ),
                    detail={"knowledge_id": skill_id, "pathway": "experiential"},
                )
        except Exception:
            logger.exception("Forced-draft safety alert emission failed (skill still created)")
    insert_knowledge(
        knowledge_id=skill_id,
        intelligence_ids=intel_ids,
        signals=cluster_signals,
        category="skill",
        name=sk_name,
        content=sk_proc,
        summary=sk_trigger[:1024],
        embedding=embedding or centroid,
        tags=skill_data.get("tags", []),
        metadata=metadata,
        source_pathway="experiential",
        source_ai_interaction_ids=processed_ids,
        extraction_confidence=confidence,
        evidence_breadth=len(entity_ids),
        status=status,
        source_links=sources,
    )
    logger.info(f"Created skill '{sk_name}' [{status}] (entities={len(entity_ids)})")


async def _generate_skills(entity_type: str, intel_context: str, ai_context: str,
                           entity_count: int, policy: dict) -> Optional[list]:
    """LLM call to extract skills from clustered intelligence + AI telemetry.
    Prompt is admin-editable via the skill_generation node (seeded with this default)."""
    from services.config_helpers import get_task_system_prompt
    system_prompt = (get_task_system_prompt("skill_generation", fallback=_SKILL_GEN_PROMPT) or _SKILL_GEN_PROMPT)
    system_prompt = system_prompt.replace("{entity_count}", str(entity_count)).replace("{entity_type}", entity_type)
    system_prompt += "\n\n" + facet_prompt_instructions()
    # TASK-262: both context blocks are derived from externally-authored
    # content — frame as untrusted data so embedded directives stay data.
    user_msg = (
        "--- Intelligence Cluster ---\n"
        + frame_untrusted("clustered intelligence", intel_context, limit=4500)
    )
    if ai_context:
        user_msg += "\n" + frame_untrusted("AI agent telemetry", ai_context, limit=1200)

    try:
        result_text = await call_llm(
            user_msg,
            system_prompt=system_prompt,
            max_tokens=int(policy["max_tokens"]),
            task_type="skill_generation",
        )
        skills = parse_llm_json(result_text, context="skill_generation")
        if not isinstance(skills, list):
            skills = [skills]
        return skills
    except Exception as e:
        logger.error(f"Skill generation LLM call failed: {e}")
        return None


def _mark_processed(interaction_ids: list):
    """Mark AI interactions as processed by skill extraction."""
    if not interaction_ids:
        return
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        for iid in interaction_ids:
            cursor.execute(
                "INSERT INTO skill_processed_interactions (interaction_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (iid,)
            )
