"""Hermes: Admin instruction parser and router.

Parses natural language admin instructions and creates knowledge,
skill, or playbook records in the unified knowledge table.
"""
import json
import logging
import uuid
from typing import Optional

from memory_services import call_llm, generate_embedding, get_memory_settings
from memory_dedup import find_similar_existing, increment_merge, compute_quality_score
from memory_db_writes import insert_knowledge

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
        '"summary": "...", "tags": [...], "confidence": 0.0-1.0, '
        '"skill_type": "soft|hard" (only for skill), '
        '"trigger_conditions": [...] (only for playbook), '
        '"steps": [{"order": 1, "action": "..."}] (only for playbook)}'
    )

    try:
        result_text = await call_llm(
            instruction[:2000],
            system_prompt=system_prompt,
            max_tokens=800,
            task_type="admin_instruct",
        )
        result = json.loads(result_text)
    except Exception as e:
        logger.error(f"Hermes instruction parsing failed: {e}")
        return {"status": "error", "message": str(e)}

    determined_category = category or result.get("category", "trade_knowledge")
    confidence = result.get("confidence", 0.5)
    name = result.get("name", "Admin Instruction")
    content = result.get("content", instruction)
    summary = result.get("summary", "")
    tags = result.get("tags", [])

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

    # Generate embedding
    embedding = None
    try:
        embedding = await generate_embedding(f"{name}. {summary or content}")
    except Exception:
        pass

    # Dedup check
    settings = get_memory_settings()
    threshold = settings.get("dedup_similarity_threshold", 0.85)
    if embedding:
        existing = await find_similar_existing(embedding, threshold, category=determined_category)
        if existing:
            increment_merge(existing)
            return {"status": "merged", "id": existing, "category": determined_category}

    # Insert
    quality = compute_quality_score(0.5, 0.0, confidence, 0, 0.0)
    knowledge_id = str(uuid.uuid4())
    status = "active" if auto_activate else "draft"
    insert_knowledge(
        knowledge_id=knowledge_id,
        intelligence_ids=[],
        knowledge_type=determined_category,
        category=determined_category,
        name=name,
        content=content,
        summary=summary,
        embedding=embedding,
        tags=tags,
        source_pathway="admin_instructed",
        extraction_confidence=confidence,
        quality_score=quality,
        status=status,
        metadata=metadata or None,
    )
    logger.info(f"Hermes created {determined_category} '{name}' [{status}]")
    return {"status": "created", "id": knowledge_id, "category": determined_category}
