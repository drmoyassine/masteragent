"""Knowledge generation: intelligence → knowledge via PII scrub + LLM synthesis."""
import logging
import uuid

from core.storage import get_memory_db_context
from memory_services import (
    call_llm,
    generate_embedding,
    get_memory_settings,
    get_system_prompt,
    scrub_pii,
)
from services.config_helpers import get_pipeline_configs, get_system_prompt_by_config_id
from services.llm import parse_llm_json
from services.prompt_renderer import inject_variables
from memory_db_writes import insert_knowledge, log_pipeline_run
from memory_prior_context import fetch_prior_knowledge_semantic
from memory_helpers import _get_entity_type_config, _format_signal_definitions

logger = logging.getLogger(__name__)


async def run_knowledge_check(drain: bool = False):
    """Check if enough confirmed intelligence have accumulated to generate a Knowledge.

    Each pass consumes at most one threshold-sized batch per entity type. With
    drain=True the check repeats until the backlog no longer yields a batch
    (safety-capped) — used for backfilling a long-accumulated backlog."""
    max_rounds = 50 if drain else 1
    total_created = 0
    for round_no in range(max_rounds):
        created = await _run_knowledge_check_once()
        total_created += created
        if not created:
            break
        if drain:
            logger.info(f"Knowledge drain round {round_no + 1}: created {created} record(s), continuing")
    if drain:
        logger.info(f"Knowledge drain complete: {total_created} record(s) created")
    return total_created


async def _run_knowledge_check_once() -> int:
    """Single knowledge-check pass. Returns the number of knowledge records created."""
    settings = get_memory_settings()
    global_knowledge_threshold = settings.get("knowledge_threshold", 5)
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
            threshold = config.get("knowledge_extraction_threshold") or global_knowledge_threshold

            if count >= threshold:
                cursor.execute("""
                    SELECT i.id, i.name, i.content, i.summary, i.signals, i.created_at
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
    prior_knowledge_count = settings.get("prior_knowledge_semantic_count", 3)
    prior_knowledge_text = await fetch_prior_knowledge_semantic(
        context, prior_knowledge_count,
        log_label="prior knowledge for deduplication",
    )

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
            "Set \"signals\" to one or more of the defined signal names provided below."
        )

    entity_type = intelligence[0].get("primary_entity_type", "") if intelligence else ""
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

    try:
        user_msg_parts = []
        if prior_knowledge_text:
            user_msg_parts.append(f"--- Existing Knowledge (do NOT duplicate or repeat these) ---\n{prior_knowledge_text}")
        user_msg_parts.append(f"--- Intelligence Items to Synthesize ---\n{context}")
        user_msg = "\n\n".join(user_msg_parts)

        result_text = await call_llm(
            user_msg[:8000],
            system_prompt=system_prompt,
            max_tokens=settings.get("knowledge_max_tokens") or 1200,
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
    signals = list(dict.fromkeys(signals))

    if not content:
        return 0

    embedding = None
    try:
        embedding = await generate_embedding(f"{name}. {summary or content}")
    except Exception as e:
        logger.warning(f"Knowledge embedding failed: {e}")

    # WS-4: extract governed facets into metadata.facets (best-effort, never blocks)
    from memory_facets import enrich_metadata_with_facets
    metadata = await enrich_metadata_with_facets(None, name, content, summary)

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
    )
    logger.info(f"Generated Knowledge {knowledge_id} from {len(intelligence_ids)} intelligence")
    return 1


async def promote_to_knowledge(insight_id: str):
    """PII scrub + generalize a single Intelligence and write it as a Knowledge.
    Kept for manual admin promotion — not used by the automatic Knowledge accumulation path."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, primary_entity_type, primary_entity_id, source_memory_ids,
                   signals, name, content, summary
            FROM intelligence WHERE id = %s
        """, (insight_id,))
        Intelligence = cursor.fetchone()

    if not Intelligence:
        logger.warning(f"promote_to_knowledge: Intelligence {insight_id} not found")
        return

    content = Intelligence["content"]
    summary = Intelligence["summary"] or ""

    try:
        content = await scrub_pii(content)
        summary = await scrub_pii(summary) if summary else ""
    except Exception as e:
        logger.warning(f"PII scrub failed for Intelligence {insight_id}: {e}")

    generalize_prompt = (
        "You are an AI editor. Remove all specific entity names, organization names, and other "
        "identifying information from the following text, replacing with generic terms (e.g., 'the client', "
        "'the institution'). Preserve the Intelligence's meaning. Return only the edited text."
    )
    try:
        content = await call_llm(
            content,
            system_prompt=generalize_prompt,
            max_tokens=get_memory_settings().get("knowledge_max_tokens") or 1200,
            task_type="knowledge_generation"
        )
    except Exception as e:
        logger.warning(f"Knowledge generalization failed: {e}")

    embedding = None
    try:
        embedding = await generate_embedding(f"{Intelligence['name']}. {summary or content}")
    except Exception as e:
        logger.warning(f"Knowledge embedding failed: {e}")

    knowledge_id = str(uuid.uuid4())
    insert_knowledge(
        knowledge_id=knowledge_id,
        intelligence_ids=[insight_id],
        signals=Intelligence.get("signals") or [],
        name=Intelligence["name"],
        content=content,
        summary=summary,
        embedding=embedding,
        tags=[],
    )
    logger.info(f"Promoted Intelligence {insight_id} to Knowledge {knowledge_id}")
