"""Intelligence generation (compaction): memories → intelligence via LLM."""
import json
import logging
import uuid

from core.storage import get_memory_db_context
from memory_services import (
    call_llm,
    generate_embedding,
    get_llm_config,
    get_memory_settings,
    get_system_prompt,
)
from services.config_helpers import get_pipeline_configs, get_system_prompt_by_config_id
from services.prompt_renderer import inject_variables
from memory_db_writes import insert_intelligence
from memory_prior_context import fetch_prior_intelligence, fetch_prior_knowledge_semantic
from memory_helpers import _get_entity_type_config, _format_signal_definitions

logger = logging.getLogger(__name__)


async def run_compaction_check():
    """Check all entities for compaction threshold and trigger if needed."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT primary_entity_type, primary_entity_id, COUNT(*) as uncompacted_count
            FROM memories
            WHERE compacted = FALSE
            GROUP BY primary_entity_type, primary_entity_id
        """)
        entities = cursor.fetchall()

    for row in entities:
        entity_type = row["primary_entity_type"]
        entity_id = row["primary_entity_id"]
        config = _get_entity_type_config(entity_type)
        try:
            await _check_compaction_trigger(entity_type, entity_id, config)
        except Exception as e:
            logger.error(f"Compaction check failed for {entity_type}/{entity_id}: {e}")


async def _check_compaction_trigger(entity_type: str, entity_id: str, config: dict):
    """Check whether compaction should trigger for this entity.
    Fires if Uncompacted memory count >= intelligence_extraction_threshold."""
    settings = get_memory_settings()
    global_threshold = settings.get("intelligence_extraction_threshold", 10)
    threshold = config.get("intelligence_extraction_threshold") or global_threshold

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt
            FROM memories
            WHERE primary_entity_type = %s AND primary_entity_id = %s AND compacted = FALSE
        """, (entity_type, entity_id))
        count = cursor.fetchone()["cnt"]

    if count >= threshold:
        logger.info(f"Intelligence extraction trigger enqueue for {entity_type}/{entity_id}: {count} memories")
        from memory.queue import knowledge_queue
        await knowledge_queue.add(
            "generate_insight",
            {"entity_type": entity_type, "entity_id": entity_id},
            {"priority": 4}
        )


async def compact_entity(entity_type: str, entity_id: str):
    """Generate an Intelligence from the N most recent uncompacted memories."""
    config = _get_entity_type_config(entity_type)
    threshold = config.get("compaction_threshold", 10)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, content_summary, related_entities, intents
            FROM memories
            WHERE primary_entity_type = %s AND primary_entity_id = %s
              AND compacted = FALSE
            ORDER BY date ASC
            LIMIT %s
        """, (entity_type, entity_id, threshold))
        memories = [dict(r) for r in cursor.fetchall()]

    if not memories:
        return

    memory_ids = [m["id"] for m in memories]

    context_parts = []
    for m in memories:
        related = m.get("related_entities") or []
        if isinstance(related, str):
            related = json.loads(related)
        signals = m.get("intents") or []
        context_parts.append(
            f"[{m['date']}] {m.get('content_summary', '')}\n"
            f"  Entities: {', '.join(e.get('name', '') for e in related if isinstance(e, dict))}\n"
            f"  Signals: {', '.join(signals)}"
        )

    context = "\n\n".join(context_parts)

    settings = get_memory_settings()
    prior_intelligence_text = await fetch_prior_intelligence(entity_type, entity_id, context)

    prior_knowledge_in_intel = settings.get("prior_knowledge_in_intelligence_count", 2)
    prior_knowledge_text = await fetch_prior_knowledge_semantic(
        context, prior_knowledge_in_intel,
        log_label=f"prior knowledge for intelligence ({entity_type}/{entity_id})",
    )

    pipeline_nodes = get_pipeline_configs("intelligence")
    pk_gen_node = next((n for n in pipeline_nodes if n["task_type"] == "intelligence_generation"), None)

    if pk_gen_node:
        system_prompt = get_system_prompt_by_config_id(pk_gen_node["id"])
        node_id = pk_gen_node["id"]
    else:
        system_prompt = await get_system_prompt("intelligence_generation")
        node_id = None

    if not system_prompt:
        system_prompt = (
            "You are an AI analyst. Based on the provided memory summaries, identify 1 to 3 distinct, meaningful "
            "patterns, risks, opportunities, or behavioral signals. Only include what is genuinely supported by the data "
            "— do not force multiple signals if only one is meaningful. "
            "Return a JSON array only (even for a single result): "
            "[{\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\"}]"
        )
    intel_signals = config.get("intelligence_signals_prompt") or []
    system_prompt = inject_variables(system_prompt, {
        "entity": {"type": entity_type, "id": entity_id},
        "intelligence_signals": _format_signal_definitions(intel_signals),
    })

    if not pk_gen_node:
        llm_config = get_llm_config("intelligence_generation") or get_llm_config("intelligence_generation")
        if not llm_config:
            logger.warning(f"No LLM config for intelligence_generation — skipping compaction for {entity_type}/{entity_id}")
            return

    try:
        user_msg_parts = [f"Entity: {entity_type} / {entity_id}"]
        if prior_knowledge_text:
            user_msg_parts.append(f"--- Established Knowledge (organizational patterns already known) ---\n{prior_knowledge_text}")
        if prior_intelligence_text:
            user_msg_parts.append(f"--- Existing Intelligence for this entity (do NOT duplicate) ---\n{prior_intelligence_text}")
        user_msg_parts.append(f"--- Memory Summaries to Analyze ---\n{context}")
        user_msg = "\n\n".join(user_msg_parts)
        result_text = await call_llm(
            user_msg,
            system_prompt=system_prompt,
            max_tokens=1200,
            config_id=node_id,
            task_type="intelligence_generation"
        )
        parsed = json.loads(result_text)
        # Support both array (1-3 signals) and legacy single-object responses
        results = parsed if isinstance(parsed, list) else [parsed]
    except Exception as e:
        logger.error(f"Intelligence LLM call failed: {e}")
        return

    auto_approve = config.get("intelligence_auto_approve", False)
    status = "confirmed" if auto_approve else "draft"
    created = 0

    for result in results[:3]:
        name = result.get("name", "Unnamed Intelligence")
        knowledge_type = result.get("knowledge_type", "other")
        content = result.get("content", "")
        summary = result.get("summary", "")

        if not content:
            continue

        embedding = None
        try:
            embedding = await generate_embedding(f"{name}. {summary or content}")
        except Exception as e:
            logger.warning(f"Intelligence embedding failed: {e}")

        insight_id = str(uuid.uuid4())
        insert_intelligence(
            insight_id=insight_id,
            entity_type=entity_type,
            entity_id=entity_id,
            memory_ids=memory_ids,
            knowledge_type=knowledge_type,
            name=name,
            content=content,
            summary=summary,
            embedding=embedding,
            auto_approve=auto_approve,
        )
        created += 1

    logger.info(f"Created {created} Intelligence item(s) ({status}) for {entity_type}/{entity_id} from {len(memory_ids)} memories")
