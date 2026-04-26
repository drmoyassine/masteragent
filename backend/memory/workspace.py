"""
memory/workspace.py — Entity Workspace Chat

Per-entity LLM chat endpoint. Provides a conversational interface
scoped to a specific entity, enriched with memory context (memories,
intelligence, knowledge).

Endpoints:
  POST /workspace/{entity_type}/{entity_id}/chat        — agent key auth
  POST /workspace/{entity_type}/{entity_id}/chat/admin  — admin JWT auth

Flow:
  1. Embed user message for semantic retrieval
  2. Fan-out search: memories + intelligence + knowledge
  3. Build context + system prompt (Prompt Manager skill if provided)
  4. Call LLM (history included)
  5. Parse structured actions from LLM response (create_intelligence, update_intelligence)
  6. Execute actions
  7. Log exchange as interaction_type="ai_conversation"
  8. Return {response, actions_taken, interaction_id, context_summary}
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.storage import get_memory_db_context, cache_interaction
from memory_services import (
    call_llm,
    generate_embedding,
    get_system_prompt,
    search_memories_by_vector,
    search_intelligence_by_vector,
    search_knowledge_by_vector,
)
from memory.auth import require_agent_auth, require_admin_auth

router = APIRouter()
logger = logging.getLogger(__name__)

_MAX_CONTEXT_MEMORIES = 5
_MAX_CONTEXT_INSIGHTS = 3
_MAX_CONTEXT_LESSONS = 3
_MAX_HISTORY_TURNS = 10


# ─────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str       # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []
    skill_name: Optional[str] = None    # Prompt Manager skill to use as system prompt
    include_lessons: bool = True        # Include generalised knowledge in context
    stream: bool = False                # Reserved for future streaming support

class ActionResult(BaseModel):
    action: str
    result: str
    id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    interaction_id: str
    actions_taken: List[ActionResult] = []
    context_summary: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/workspace/{entity_type}/{entity_id}/chat", response_model=ChatResponse)
async def entity_workspace_chat(
    entity_type: str,
    entity_id: str,
    body: ChatRequest,
    caller: dict = Depends(require_agent_auth),
):
    """
    Conversational chat scoped to a specific entity (agent key auth).
    Retrieves relevant memories, intelligence, and knowledge for context.
    """
    return await _run_chat(entity_type, entity_id, body, caller)


@router.post("/workspace/{entity_type}/{entity_id}/chat/admin", response_model=ChatResponse)
async def entity_workspace_chat_admin(
    entity_type: str,
    entity_id: str,
    body: ChatRequest,
    admin: dict = Depends(require_admin_auth),
):
    """Same as agent workspace but authenticated with admin JWT."""
    synthetic_caller = {"id": "admin", "name": "admin", **admin}
    return await _run_chat(entity_type, entity_id, body, synthetic_caller)


# ─────────────────────────────────────────────────────────────
# Core chat logic
# ─────────────────────────────────────────────────────────────

async def _run_chat(
    entity_type: str,
    entity_id: str,
    body: ChatRequest,
    caller: Optional[dict],
) -> ChatResponse:
    """Shared pipeline for both agent and admin workspace chat."""
    now = datetime.now(timezone.utc).isoformat()
    interaction_id = str(uuid.uuid4())

    # ── 1. Embed the user's message ───────────────────────────────────────
    query_embedding = None
    try:
        query_embedding = await generate_embedding(body.message)
    except Exception as e:
        logger.warning(f"Workspace embedding failed: {e}")

    # ── 2. Retrieve entity context ────────────────────────────────────────
    memories, intelligence, knowledge = [], [], []

    if query_embedding:
        try:
            memories = await search_memories_by_vector(
                query_embedding, entity_id=entity_id, limit=_MAX_CONTEXT_MEMORIES
            )
        except Exception as e:
            logger.warning(f"Memory search failed: {e}")

        try:
            intelligence = await search_intelligence_by_vector(
                query_embedding, entity_id=entity_id, limit=_MAX_CONTEXT_INSIGHTS
            )
        except Exception as e:
            logger.warning(f"Intelligence search failed: {e}")

        if body.include_lessons:
            try:
                knowledge = await search_knowledge_by_vector(
                    query_embedding, limit=_MAX_CONTEXT_LESSONS
                )
            except Exception as e:
                logger.warning(f"Knowledge search failed: {e}")

    # ── 3. Build context block ────────────────────────────────────────────
    context_sections = []

    if memories:
        mem_bullets = "\n".join(
            f"  • [{m.get('date', '?')}] {m.get('content_summary', '')}"
            for m in memories
        )
        context_sections.append(f"### Recent Memory Summaries\n{mem_bullets}")

    if intelligence:
        ins_bullets = "\n".join(
            f"  • [{i.get('knowledge_type', 'Intelligence')}] {i.get('name', '')}: "
            f"{i.get('summary') or i.get('content', '')[:200]}"
            for i in intelligence
        )
        context_sections.append(f"### Known intelligence\n{ins_bullets}")

    if knowledge:
        les_bullets = "\n".join(
            f"  • [{l.get('knowledge_type', 'Knowledge')}] {l.get('name', '')}: "
            f"{l.get('summary') or l.get('content', '')[:200]}"
            for l in knowledge
        )
        context_sections.append(f"### Relevant General knowledge\n{les_bullets}")

    entity_context = "\n\n".join(context_sections)
    context_summary = (
        f"{len(memories)} memories, {len(intelligence)} intelligence, {len(knowledge)} knowledge"
        if entity_context else None
    )

    # ── 4. Resolve system prompt ──────────────────────────────────────────
    if body.skill_name:
        system_prompt_text = await _get_skill_prompt(body.skill_name)
    else:
        system_prompt_text = await get_system_prompt("entity_workspace") or (
            "You are an intelligent assistant helping manage a relationship with a specific entity. "
            "Use the provided memory context to give personalized, accurate answers. "
            "You may suggest creating an Intelligence or updating existing intelligence by including structured "
            "actions in your reply (see the action syntax below)."
        )

    from services.prompt_renderer import inject_variables
    system_prompt_text = inject_variables(system_prompt_text, {
        "entity": {"type": entity_type, "id": entity_id}
    })

    if entity_context:
        system_prompt_text = (
            f"{system_prompt_text}\n\n"
            f"## Entity Context: {entity_type.title()} / {entity_id}\n\n"
            f"{entity_context}\n\n"
            "---\n"
            "To create or update an Intelligence, include a JSON block in your reply:\n"
            "```action\n"
            '{"type": "create_intelligence", "name": "...", "knowledge_type": "...", "content": "..."}\n'
            "```"
        )

    # ── 5. Call LLM ──────────────────────────────────────────────────────
    try:
        response_text = await call_llm(
            body.message,
            system_prompt=system_prompt_text,
            max_tokens=1200,
            task_type="intelligence_generation",
        )
    except Exception as e:
        logger.error(f"Workspace LLM call failed: {e}")
        raise HTTPException(status_code=503, detail="LLM call failed")

    if not response_text:
        raise HTTPException(status_code=503, detail="LLM returned empty response")

    # ── 6. Parse + execute structured actions ─────────────────────────────
    actions_taken = await _execute_actions(response_text, entity_type, entity_id, caller)

    # ── 7. Log the conversation as an interaction ─────────────────────────
    agent_id = caller.get("id") if caller else None
    agent_name = caller.get("name") if caller else "workspace"

    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO interactions (
                    id, timestamp, interaction_type, agent_id, agent_name,
                    content, primary_entity_type, primary_entity_id,
                    metadata, source, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                interaction_id, now, "ai_conversation",
                agent_id, agent_name,
                json.dumps({"user": body.message, "assistant": response_text, "skill": body.skill_name}),
                entity_type, entity_id,
                json.dumps({"skill": body.skill_name, "actions_taken": len(actions_taken)}),
                "workspace",
                "done",     # ai_conversation goes straight to done (no NER needed)
                now,
            ))

        cache_interaction(interaction_id, {
            "id": interaction_id,
            "interaction_type": "ai_conversation",
            "primary_entity_type": entity_type,
            "primary_entity_id": entity_id,
            "timestamp": now,
            "source": "workspace",
        })
    except Exception as e:
        logger.warning(f"Failed to log workspace interaction: {e}")

    return ChatResponse(
        response=response_text,
        interaction_id=interaction_id,
        actions_taken=actions_taken,
        context_summary=context_summary,
    )


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _get_skill_prompt(skill_name: str) -> str:
    """
    Retrieve a skill's system prompt content from the Prompt Manager.
    Falls back to a generic prompt if skill not found.
    """
    try:
        from core.db import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pv.content
                FROM prompt_versions pv
                JOIN prompts p ON p.id = pv.prompt_id
                WHERE p.name = %s AND pv.is_default = TRUE
                LIMIT 1
            """, (skill_name,))
            row = cursor.fetchone()
            if row:
                return row["content"]
    except Exception as e:
        logger.warning(f"Could not load skill '{skill_name}': {e}")

    return (
        f"You are a specialized assistant using the '{skill_name}' skill. "
        "Help the user based on the entity context provided."
    )


async def _execute_actions(
    response_text: str,
    entity_type: str,
    entity_id: str,
    caller: Optional[dict],
) -> List[ActionResult]:
    """
    Parse ```action {...}``` blocks from LLM response and execute them.

    Supported actions:
      - create_intelligence  → {type, name, knowledge_type, content, summary?}
      - update_intelligence  → {type, id, content?, summary?, status?}
    """
    actions_taken = []
    blocks = re.findall(r"```action\s*(\{.*?\})\s*```", response_text, re.DOTALL)

    for block in blocks:
        try:
            action = json.loads(block)
            action_type = action.get("type")

            if action_type == "create_intelligence":
                insight_id = str(uuid.uuid4())
                now = datetime.now(timezone.utc).isoformat()
                with get_memory_db_context() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO intelligence (
                            id, primary_entity_type, primary_entity_id,
                            knowledge_type, name, content, summary,
                            status, created_by, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        insight_id, entity_type, entity_id,
                        action.get("knowledge_type", "other"),
                        action.get("name", "Workspace Intelligence"),
                        action.get("content", ""),
                        action.get("summary"),
                        "draft",
                        caller.get("id", "workspace") if caller else "workspace",
                        now, now,
                    ))
                actions_taken.append(ActionResult(
                    action="create_intelligence", result="created", id=insight_id
                ))

            elif action_type == "update_intelligence":
                insight_id = action.get("id")
                if not insight_id:
                    continue
                fields, values = [], []
                for k in ("content", "summary", "status"):
                    if k in action:
                        fields.append(f"{k} = %s")
                        values.append(action[k])
                if fields:
                    values.append(insight_id)
                    with get_memory_db_context() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            f"UPDATE intelligence SET {', '.join(fields)} WHERE id = %s",
                            values
                        )
                    actions_taken.append(ActionResult(
                        action="update_intelligence", result="updated", id=insight_id
                    ))

        except Exception as e:
            logger.warning(f"Workspace action error: {e}")

    return actions_taken


