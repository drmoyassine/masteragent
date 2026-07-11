"""Hermes: Admin instruction parser and router.

Parses natural language admin instructions and creates knowledge,
skill, or playbook records in the unified knowledge table.
"""
import logging
import uuid
from typing import Optional

from memory_services import call_llm, generate_embedding, get_memory_settings
from services.llm import parse_llm_json
from memory_db_writes import insert_knowledge
from memory_generation_policy import approval_status, resolve_generation_policy
from memory_facets import facet_prompt_instructions, validate_generated_facets

logger = logging.getLogger(__name__)


async def process_admin_instruction(
    instruction: str,
    target: str = "auto",
    category: Optional[str] = None,
    entity_type: Optional[str] = None,
    auto_activate: bool = False,
) -> dict:
    """Parse an admin instruction and create the appropriate knowledge record.

    Returns {"status": "created"|"merged", "id": "...", "category": "..."}
    """
    system_prompt = (
        "You are Hermes, an intelligent assistant that parses admin instructions "
        "into structured knowledge records for a CRM memory system.\n\n"
        "Determine whether the instruction is best represented as:\n"
        "- best_practices: A behavioral rule or Dos and Don'ts\n"
        "- lessons_learned: A negative outcome with root-cause analysis\n"
        "- trade_knowledge: A domain-specific procedural or regulatory fact\n"
        "- skill: A discrete, composable capability (specify skill_type: soft or hard)\n"
        "- playbook: An ordered procedure with trigger conditions\n\n"
        'Return JSON: {"category": "...", "name": "...", "content": "...", '
        '"summary": "...", "tags": [...], "signals": [...], "confidence": 0.0-1.0, '
        '"skill_type": "soft|hard" (only for skill), '
        '"trigger_conditions": [...] (only for playbook), '
        '"steps": [{"order": 1, "action": "..."}] (only for playbook)}. '
        '"signals" are the domain topics this record relates to.'
    )
    system_prompt += "\n\n" + facet_prompt_instructions()

    settings = get_memory_settings() or {}
    policy = resolve_generation_policy("manual_creation", settings=settings)["values"]

    try:
        result_text = await call_llm(
            instruction[:2000],
            system_prompt=system_prompt,
            max_tokens=int(policy["max_tokens"]),
            task_type="admin_instruct",
        )
        result = parse_llm_json(result_text, context="admin_instruct")
    except Exception as e:
        logger.error(f"Hermes instruction parsing failed: {e}")
        return {"status": "error", "message": str(e)}

    determined_category = category or result.get("category", "trade_knowledge")
    confidence = result.get("confidence", 0.5)
    if float(confidence) < float(policy["min_confidence"]):
        return {"status": "skipped", "reason": "below_confidence", "confidence": confidence}
    name = result.get("name", "Admin Instruction")
    content = result.get("content", instruction)
    summary = result.get("summary", "")
    tags = result.get("tags", [])
    signals = result.get("signals", [])
    if isinstance(signals, str):
        signals = [s.strip() for s in signals.split(",") if s.strip()]

    # Build metadata for skill/playbook categories
    metadata = {}
    if determined_category == "skill":
        metadata = {
            "skill_type": result.get("skill_type", "hard"),
            "trigger_desc": result.get("trigger_desc", ""),
            "procedure": content,
            "entity_types": [entity_type] if entity_type else [],
            "playbook_ids": [],
        }
    elif determined_category == "playbook":
        metadata = {
            "entity_type": entity_type or "contact",
            "signal_type": None,
            "trigger_conditions": result.get("trigger_conditions", []),
            "steps": result.get("steps", []),
            "skill_ids": [],
        }

    # Generate embedding via the canonical category-aware serializer.
    embedding = None
    try:
        from memory_embedding import embed_knowledge_fields
        embedding, _model = await embed_knowledge_fields(
            name=name, category=determined_category, content=content, summary=summary,
        )
    except Exception:
        pass

    knowledge_id = str(uuid.uuid4())
    status = "active" if auto_activate else approval_status(policy["approval_policy"])
    facets, facet_state = validate_generated_facets(result.get("facets") or {})
    metadata["facets"] = facets
    metadata["facet_extraction"] = facet_state
    insert_knowledge(
        knowledge_id=knowledge_id,
        intelligence_ids=[],
        signals=signals,
        category=determined_category,
        name=name,
        content=content,
        summary=summary,
        embedding=embedding,
        tags=tags,
        source_pathway="admin_instructed",
        extraction_confidence=confidence,
        status=status,
        metadata=metadata or None,
        approved_by_type="user",
        approval_origin="admin_instruction",
    )
    logger.info(f"Hermes created {determined_category} '{name}' [{status}]")
    return {"status": "created", "id": knowledge_id, "category": determined_category}
