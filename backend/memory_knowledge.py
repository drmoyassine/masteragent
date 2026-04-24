"""Knowledge generation: intelligence → knowledge via PII scrub + LLM synthesis."""
import json
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
from services.prompt_renderer import inject_variables
from memory_db_writes import insert_knowledge
from memory_prior_context import fetch_prior_knowledge_semantic
from memory_helpers import _get_entity_type_config, _format_signal_definitions

logger = logging.getLogger(__name__)


async def run_lesson_check():
    """Check if enough confirmed intelligence have accumulated to generate a Knowledge."""
    settings = get_memory_settings()
    global_knowledge_threshold = settings.get("knowledge_threshold", 5)

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
                    SELECT i.id, i.name, i.content, i.summary, i.knowledge_type, i.created_at
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
                await generate_knowledge_from_intelligence(batch)


async def generate_knowledge_from_intelligence(intelligence: list):
    """Generate a Knowledge from a batch of confirmed intelligence."""
    if not intelligence:
        return

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
            f"[{ins.get('knowledge_type', 'other')}] {ins.get('name', '')}\n{content}"
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
        system_prompt = "You are an AI knowledge curator. Synthesize into generalizable Knowledge. Return JSON: {\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\", \"tags\": [...]}"

    entity_type = intelligence[0].get("primary_entity_type", "") if intelligence else ""
    know_signals_text = ""
    if entity_type:
        know_config = _get_entity_type_config(entity_type)
        know_signals = know_config.get("knowledge_signals_prompt") or []
        know_signals_text = _format_signal_definitions(know_signals)
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
            max_tokens=600,
            config_id=node_id,
            task_type="knowledge_generation",
        )
        result = json.loads(result_text)
    except Exception as e:
        logger.error(f"Knowledge generation LLM call failed: {e}")
        return

    name = result.get("name", "Unnamed Knowledge")
    knowledge_type = result.get("knowledge_type", "other")
    content = result.get("content", "")
    summary = result.get("summary", "")
    tags = result.get("tags", [])

    if not content:
        return

    embedding = None
    try:
        embedding = await generate_embedding(f"{name}. {summary or content}")
    except Exception as e:
        logger.warning(f"Knowledge embedding failed: {e}")

    knowledge_id = str(uuid.uuid4())
    insert_knowledge(
        knowledge_id=knowledge_id,
        intelligence_ids=intelligence_ids,
        knowledge_type=knowledge_type,
        name=name,
        content=content,
        summary=summary,
        embedding=embedding,
        tags=tags,
    )
    logger.info(f"Generated Knowledge {knowledge_id} from {len(intelligence_ids)} intelligence")


async def promote_to_knowledge(insight_id: str):
    """PII scrub + generalize a single Intelligence and write it as a Knowledge.
    Kept for manual admin promotion — not used by the automatic Knowledge accumulation path."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, primary_entity_type, primary_entity_id, source_memory_ids,
                   knowledge_type, name, content, summary
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
            max_tokens=600,
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
        knowledge_type=Intelligence["knowledge_type"],
        name=Intelligence["name"],
        content=content,
        summary=summary,
        embedding=embedding,
        tags=[],
    )
    logger.info(f"Promoted Intelligence {insight_id} to Knowledge {knowledge_id}")
