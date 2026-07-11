"""Knowledge generation: intelligence → knowledge via PII scrub + LLM synthesis."""
import logging
import uuid
from typing import Optional

from core.storage import get_memory_db_context
from memory_services import (
    call_llm,
    get_memory_settings,
    get_system_prompt,
    scrub_pii,
)
from services.config_helpers import get_pipeline_configs, get_system_prompt_by_config_id
from services.llm import parse_llm_json
from services.prompt_renderer import inject_variables
from memory_db_writes import insert_knowledge, log_pipeline_run
from memory_helpers import _get_entity_type_config, _format_signal_definitions
from memory_generation_policy import approval_status, resolve_generation_policy
from memory_facets import facet_prompt_instructions, validate_generated_facets

logger = logging.getLogger(__name__)


async def run_knowledge_check(drain: bool = False, min_count: Optional[int] = None):
    """Check if enough confirmed intelligence have accumulated to generate a Knowledge.

    Each pass consumes at most one threshold-sized batch per entity type. With
    drain=True the check repeats until the backlog no longer yields a batch
    (safety-capped) — used for backfilling a long-accumulated backlog.

    min_count (nightly schedule floor) overrides the per-type knowledge threshold,
    so entity types below the main threshold still get reflected on nightly."""
    max_rounds = 50 if drain else 1
    total_created = 0
    for round_no in range(max_rounds):
        created = await _run_knowledge_check_once(min_count=min_count)
        total_created += created
        if not created:
            break
        if drain:
            logger.info(f"Knowledge drain round {round_no + 1}: created {created} record(s), continuing")
    if drain:
        logger.info(f"Knowledge drain complete: {total_created} record(s) created")
    return total_created


async def _run_knowledge_check_once(min_count: Optional[int] = None) -> int:
    """Single knowledge-check pass. Returns the number of knowledge records created.
    min_count overrides the effective threshold (nightly schedule floor)."""
    settings = get_memory_settings()
    global_knowledge_threshold = settings.get(
        "knowledge_generation_evidence_threshold", settings.get("knowledge_threshold", 5),
    )
    created = 0

    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT primary_entity_type, COUNT(*) as unused_count
            FROM intelligence i
            WHERE i.status = 'confirmed'
              AND NOT EXISTS (
                  SELECT 1 FROM knowledge l
                  WHERE i.id = ANY(l.source_intelligence_ids)
              )
            GROUP BY primary_entity_type
        """)
        entities = cursor.fetchall()

        for row in entities:
            entity_type = row["primary_entity_type"]
            count = row["unused_count"]

            config = _get_entity_type_config(entity_type)
            policy = resolve_generation_policy(
                "declarative_knowledge", settings=settings, entity_config=config,
            )["values"]
            if not policy["enabled"]:
                continue
            threshold = config.get("knowledge_extraction_threshold") or policy["evidence_threshold"] or global_knowledge_threshold
            # Nightly schedule floor overrides the main threshold (reflect on
            # sub-threshold piles). Batch size still capped at the floor value.
            if min_count is not None:
                threshold = min_count

            if count >= threshold:
                cursor.execute("""
                    SELECT i.id, i.name, i.content, i.summary, i.signals, i.created_at,
                           i.primary_entity_type, i.primary_entity_id, i.embedding,
                           i.embedding_model, i.embedding_version, i.embedding_dimensions,
                           i.embedded_at
                    FROM intelligence i
                    WHERE i.status = 'confirmed'
                      AND primary_entity_type = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM knowledge l
                          WHERE i.id = ANY(l.source_intelligence_ids)
                      )
                    ORDER BY i.created_at ASC
                    LIMIT %s
                """, (entity_type, threshold))

                batch = [dict(r) for r in cursor.fetchall()]
                logger.info(f"Knowledge extraction trigger (count) for {entity_type}: {len(batch)} unused intelligence items")
                n = await generate_knowledge_from_intelligence(batch)
                created += n
                log_pipeline_run(
                    "knowledge_check", "created" if n else "failed",
                    reason_code=None if n else "generation_failed",
                    records_created=n,
                    detail={"entity_type": entity_type, "batch": len(batch), "threshold": threshold},
                )
            else:
                log_pipeline_run(
                    "knowledge_check", "skipped", reason_code="below_threshold",
                    detail={"entity_type": entity_type, "unused_confirmed": count, "threshold": threshold},
                )
    return created


async def generate_knowledge_from_intelligence(intelligence: list) -> int:
    """Generate a Knowledge from a batch of confirmed intelligence.
    Returns 1 if a knowledge record was created, else 0."""
    if not intelligence:
        return 0

    scrubbed_parts = []
    for ins in intelligence:
        content = ins.get("content", "")
        summary = ins.get("summary", "")
        try:
            content = await scrub_pii(content)
            summary = await scrub_pii(summary) if summary else ""
        except Exception as e:
            logger.warning(f"PII scrub failed for Intelligence {ins['id']}: {e}")
        scrubbed_parts.append(
            f"[{', '.join(ins.get('signals') or []) or 'signal'}] {ins.get('name', '')}\n{content}"
        )

    context = "\n\n---\n\n".join(scrubbed_parts)
    intelligence_ids = [ins["id"] for ins in intelligence]

    settings = get_memory_settings()
    entity_type = intelligence[0].get("primary_entity_type", "") if intelligence else ""
    entity_config = _get_entity_type_config(entity_type) if entity_type else {}
    policy = resolve_generation_policy(
        "declarative_knowledge", settings=settings, entity_config=entity_config,
    )["values"]
    if not policy["enabled"]:
        log_pipeline_run("knowledge_generation", "skipped", reason_code="pathway_disabled")
        return 0

    # Cheap source-first routing happens before the generation LLM. In analysis mode
    # it records what would happen without changing the established pathway.
    sources = [{
        "source_type": "intelligence",
        "source_id": str(ins["id"]),
        "entity_id": ins.get("primary_entity_id"),
        "name": ins.get("name") or "",
        "summary": ins.get("summary") or "",
        "content": ins.get("content") or "",
        "embedding": ins.get("embedding"),
        "embedding_model": ins.get("embedding_model"),
        "embedding_version": ins.get("embedding_version"),
        "embedding_dimensions": ins.get("embedding_dimensions"),
        "embedded_at": ins.get("embedded_at"),
    } for ins in intelligence]
    route = None
    if settings.get("knowledge_evidence_routing_enabled", True):
        try:
            from memory_evidence_service import analyze_evidence, apply_high_similarity_link
            route = analyze_evidence(
                pathway="declarative_knowledge", sources=sources, settings=settings,
                entity_type=entity_type,
            )
            linked = apply_high_similarity_link(route, sources, settings)
            if linked:
                log_pipeline_run("knowledge_generation", "skipped", reason_code="evidence_linked",
                                 detail={"canonical_id": route.get("canonical_knowledge_id")})
                return 0
            if (route.get("route") == "revision_assessment" and
                    settings.get("knowledge_evidence_routing_mode") == "enforced"):
                from memory_evidence_revision_service import assess_and_apply
                revision = await assess_and_apply(route=route, sources=sources, settings=settings)
                if revision.get("action") in {"no_change", "revised"}:
                    log_pipeline_run("knowledge_generation", "revised", records_created=0,
                                     detail={"action": revision.get("action")})
                    return 0
                if revision.get("action") == "manual_review":
                    log_pipeline_run("knowledge_generation", "skipped",
                                     reason_code="revision_manual_review")
                    return 0
        except Exception as exc:
            logger.exception("Evidence routing failed; generation remains available: %s", exc)

    pipeline_nodes = get_pipeline_configs("knowledge")
    pk_gen_node = next((n for n in pipeline_nodes if n["task_type"] == "knowledge_generation"), None)
    node_id = pk_gen_node["id"] if pk_gen_node else None

    if pk_gen_node:
        system_prompt = get_system_prompt_by_config_id(pk_gen_node["id"])
    else:
        system_prompt = await get_system_prompt("knowledge_generation")

    if not system_prompt:
        system_prompt = (
            "You are an AI knowledge curator. Synthesize into generalizable Knowledge. "
            "Return JSON: {\"name\": \"...\", \"category\": \"...\", \"signals\": [\"...\"], "
            "\"content\": \"...\", \"summary\": \"...\", \"tags\": [...]}. "
            "\"category\" must be one of: best_practices, lessons_learned, trade_knowledge. "
            "Set \"signals\" to one or more of the defined signal names provided below. "
            "Emit each signal in lowercase (e.g. \"momentum\", not \"Momentum\")."
        )

    know_signals_text = ""
    valid_signals = {}
    if entity_type:
        know_config = _get_entity_type_config(entity_type)
        know_signals = know_config.get("knowledge_signals_prompt") or []
        know_signals_text = _format_signal_definitions(know_signals)
        valid_signals = {
            (s.get("name") or "").strip().lower(): (s.get("name") or "").strip()
            for s in know_signals if (s.get("name") or "").strip()
        }
    system_prompt = inject_variables(system_prompt, {
        "knowledge_signals": know_signals_text,
    })
    system_prompt += "\n\n" + facet_prompt_instructions()
    system_prompt += (
        "\nReturn confidence as a number from 0 to 1. Return governed facets in "
        "metadata.facets using the supplied schema."
    )

    try:
        result_text = await call_llm(
            f"--- Intelligence Items to Synthesize ---\n{context}"[:8000],
            system_prompt=system_prompt,
            max_tokens=int(policy["max_tokens"]),
            config_id=node_id,
            task_type="knowledge_generation",
        )
        result = parse_llm_json(result_text, context="knowledge_generation")
    except Exception as e:
        logger.error(f"Knowledge generation LLM call failed: {e}")
        return 0

    name = result.get("name", "Unnamed Knowledge")
    category = result.get("category", "trade_knowledge")
    content = result.get("content", "")
    summary = result.get("summary", "")
    tags = result.get("tags", [])
    confidence = float(result.get("confidence") or 0.0)
    if confidence < float(policy["min_confidence"]):
        log_pipeline_run("knowledge_generation", "skipped", reason_code="below_confidence",
                         detail={"confidence": confidence, "minimum": policy["min_confidence"]})
        return 0

    # Normalize signals: accept array or legacy comma-string; validate against
    # the entity type's defined knowledge signals (unknown values dropped; kept
    # verbatim only if no signals are defined for this entity type yet).
    raw_signals = result.get("signals", result.get("knowledge_type", []))
    if isinstance(raw_signals, str):
        raw_signals = [s.strip() for s in raw_signals.split(",")]
    signals = []
    for s in (raw_signals or []):
        s = (s or "").strip()
        if not s or s.lower() == "other":
            continue
        canonical = valid_signals.get(s.lower())
        if canonical:
            signals.append(canonical)
        elif not valid_signals:
            signals.append(s)
    signals = list(dict.fromkeys(s.lower() for s in signals))

    if not content:
        return 0

    embedding = None
    try:
        from memory_embedding import embed_knowledge_fields
        embedding, _model = await embed_knowledge_fields(
            name=name, category=category, content=content,
            summary=summary, signals=signals, tags=tags,
        )
    except Exception as e:
        logger.warning(f"Knowledge embedding failed: {e}")

    metadata = result.get("metadata") or {}
    facets, facet_state = validate_generated_facets(
        metadata.get("facets") or result.get("facets") or {}
    )
    metadata["facets"] = facets
    metadata["facet_extraction"] = facet_state

    knowledge_id = str(uuid.uuid4())
    insert_knowledge(
        knowledge_id=knowledge_id,
        intelligence_ids=intelligence_ids,
        signals=signals,
        category=category,
        name=name,
        content=content,
        summary=summary,
        embedding=embedding,
        tags=tags,
        metadata=metadata,
        extraction_confidence=confidence,
        status=approval_status(policy["approval_policy"]),
        evidence_breadth=len(sources),
        source_links=sources,
    )
    logger.info(f"Generated Knowledge {knowledge_id} from {len(intelligence_ids)} intelligence")
    return 1


async def promote_to_knowledge(insight_id: str):
    """Manual promotion through the same producer, evidence gate, and policy."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, primary_entity_type, primary_entity_id, source_memory_ids,
                   signals, name, content, summary, created_at, embedding,
                   embedding_model, embedding_version, embedding_dimensions, embedded_at
            FROM intelligence WHERE id = %s
        """, (insight_id,))
        intelligence = cursor.fetchone()
    if not intelligence:
        logger.warning(f"promote_to_knowledge: Intelligence {insight_id} not found")
        return 0
    return await generate_knowledge_from_intelligence([dict(intelligence)])
