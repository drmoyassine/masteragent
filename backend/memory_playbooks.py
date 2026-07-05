"""Playbook and skill extraction from intelligence clusters + AI telemetry.

Runs on a weekly cadence (or evidence-threshold override). Clusters confirmed
intelligence by cosine similarity across distinct entities, enriches clusters
with AI thoughts/tool calls from the same time window, then extracts playbooks
and decomposes them into skills — all stored in the unified knowledge table.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from core.storage import get_memory_db_context
from memory_services import call_llm, generate_embedding, get_memory_settings
from services.llm import parse_llm_json
from memory_dedup import find_similar_existing, increment_merge, compute_quality_score
from memory_db_writes import insert_knowledge, update_knowledge_quality
from memory_helpers import _get_entity_type_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Union-Find for clustering pairwise similarity results
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_playbook_check():
    """Check for playbook extraction opportunities across all entity types."""
    settings = get_memory_settings()
    threshold = settings.get("dedup_similarity_threshold", 0.85)
    confidence_min = settings.get("extraction_confidence_threshold", 0.6)

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
                  WHERE k.category = 'playbook'
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
            logger.info(f"Playbook extraction: {entity_type} has {count} unlinked intelligence (need {min_entities})")
            continue

        logger.info(f"Playbook extraction: processing {entity_type} ({count} unlinked intelligence)")
        try:
            await _process_entity_type(entity_type, threshold, confidence_min, min_entities, config)
        except Exception as e:
            logger.error(f"Playbook extraction failed for {entity_type}: {e}")


async def _process_entity_type(
    entity_type: str,
    dedup_threshold: float,
    confidence_min: float,
    min_entities: int,
    config: dict,
):
    """Cluster intelligence, enrich with AI telemetry, extract playbooks + skills."""

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
                  WHERE k.category = 'playbook'
                    AND a.id = ANY(k.source_intelligence_ids)
              )
            ORDER BY similarity DESC
            LIMIT 200
        """, (entity_type, dedup_threshold))
        pairs = [dict(r) for r in cursor.fetchall()]

    if not pairs:
        logger.info(f"No similar intelligence pairs found for {entity_type}")
        return

    # 2. Union-Find clustering
    uf = UnionFind()
    for p in pairs:
        uf.union(p["aid"], p["bid"])

    clusters = {}
    for p in pairs:
        root = uf.find(p["aid"])
        clusters.setdefault(root, set()).update([p["aid"], p["bid"]])

    # 3. Filter: cluster must span >= min_entities distinct entities
    qualifying = []
    for root, ids in clusters.items():
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT primary_entity_id FROM intelligence
                WHERE id = ANY(%s)
            """, (list(ids),))
            entity_ids = [r["primary_entity_id"] for r in cursor.fetchall()]
        if len(entity_ids) >= min_entities:
            qualifying.append((list(ids), entity_ids))

    logger.info(f"Found {len(qualifying)} qualifying clusters for {entity_type}")

    # 4. Process each qualifying cluster
    for intel_ids, entity_ids in qualifying:
        await _process_cluster(entity_type, intel_ids, entity_ids, dedup_threshold, confidence_min, config)


async def _process_cluster(
    entity_type: str,
    intel_ids: list,
    entity_ids: list,
    dedup_threshold: float,
    confidence_min: float,
    config: dict,
):
    """Enrich cluster with AI telemetry, extract playbook, decompose skills."""

    # Fetch the intelligence records
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, content, summary, signals, created_at, embedding, primary_entity_id
            FROM intelligence WHERE id = ANY(%s)
        """, (intel_ids,))
        intel_records = [dict(r) for r in cursor.fetchall()]

    # Fetch AI thoughts + tool calls for the same entities in the same time window
    min_ts = min(r["created_at"] for r in intel_records)
    max_ts = max(r["created_at"] for r in intel_records)
    # Widen window by 1 hour on each side
    window_start = (datetime.fromisoformat(min_ts) - timedelta(hours=1)).isoformat()
    window_end = (datetime.fromisoformat(max_ts) + timedelta(hours=1)).isoformat()

    ai_interactions = []
    processed_ids = []
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, interaction_type, primary_entity_id, timestamp
            FROM interactions
            WHERE interaction_type IN ('internal_ai_thought', 'internal_ai_tool_call')
              AND primary_entity_type = %s
              AND primary_entity_id = ANY(%s)
              AND timestamp BETWEEN %s AND %s
              AND NOT EXISTS (
                  SELECT 1 FROM playbook_processed_interactions p WHERE p.interaction_id = interactions.id
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

    # Compute centroid embedding for dedup check
    embeddings = [r["embedding"] for r in intel_records if r.get("embedding")]
    if not embeddings:
        return
    centroid = [sum(vals) / len(vals) for vals in zip(*embeddings)]

    # Dedup check
    existing_id = await find_similar_existing(centroid, dedup_threshold, category="playbook")
    if existing_id:
        increment_merge(existing_id)
        logger.info(f"Playbook merged into existing {existing_id} (merge_count incremented)")
        # Still mark AI interactions as processed
        _mark_processed(processed_ids)
        return

    # Generate playbook via LLM
    playbook_data = await _generate_playbook(entity_type, intel_context, ai_context, len(entity_ids))
    if not playbook_data:
        _mark_processed(processed_ids)
        return

    confidence = playbook_data.get("confidence", 0.5)
    if confidence < confidence_min:
        logger.info(f"Playbook confidence {confidence} below threshold {confidence_min} — skipping")
        _mark_processed(processed_ids)
        return

    # Determine status
    auto_activate = config.get("playbook_auto_activate", False)
    auto_score = config.get("auto_activate_score_threshold")
    quality = compute_quality_score(
        evidence_breadth_norm=min(len(entity_ids) / 10.0, 1.0),
        outcome_signal=0.0,
        confidence=confidence,
        merge_count=0,
        days_since_created=0.0,
    )
    status = "draft"
    if auto_activate and (auto_score is None or quality >= auto_score):
        status = "active"

    # Derive the playbook's domain signals from the union of its source
    # intelligence signals, so skills decomposed from it can inherit them.
    pb_signals = list(dict.fromkeys(
        s for r in intel_records for s in (r.get("signals") or [])
    ))
    playbook_data["signals"] = pb_signals

    # Insert playbook as knowledge record
    playbook_id = str(uuid.uuid4())
    metadata = {
        "entity_type": entity_type,
        "signal_type": playbook_data.get("signal_type"),
        "trigger_conditions": playbook_data.get("trigger_conditions", []),
        "steps": playbook_data.get("steps", []),
        "skill_ids": [],
    }
    insert_knowledge(
        knowledge_id=playbook_id,
        intelligence_ids=intel_ids,
        signals=pb_signals,
        category="playbook",
        name=playbook_data.get("name", "Unnamed Playbook"),
        content=playbook_data.get("description", ""),
        summary=playbook_data.get("description", "")[:200],
        embedding=centroid,
        tags=playbook_data.get("tags", []),
        source_pathway="experiential",
        source_ai_interaction_ids=processed_ids,
        extraction_confidence=confidence,
        evidence_breadth=len(entity_ids),
        quality_score=quality,
        status=status,
    )
    update_knowledge_quality(playbook_id, quality)
    logger.info(f"Created playbook '{playbook_data.get('name')}' [{status}] (score={quality:.2f}, entities={len(entity_ids)})")

    # Mark AI interactions as processed
    _mark_processed(processed_ids)

    # Decompose skills from playbook
    if playbook_data.get("steps"):
        await _generate_skills_from_playbook(playbook_id, playbook_data, entity_type, config)


async def _generate_playbook(entity_type: str, intel_context: str, ai_context: str, entity_count: int) -> Optional[dict]:
    """LLM call to extract a playbook from clustered intelligence + AI telemetry."""
    system_prompt = (
        "You are a procedural knowledge extractor for a CRM memory system.\n\n"
        "You are given a cluster of intelligence signals that were independently observed "
        f"across {entity_count} different {entity_type} entities, along with AI agent telemetry "
        "from the interactions where these signals appeared.\n\n"
        "RULES:\n"
        "- Extract 3-7 concrete, ordered action steps\n"
        "- Steps must be actionable (start with a verb)\n"
        "- Steps must be generalizable (no specific entity names)\n"
        "- Include trigger conditions: what keywords/phrases indicate this playbook applies\n"
        "- Name the playbook descriptively\n\n"
        'Return JSON: {"name": "...", "description": "...", "signal_type": "...", '
        '"trigger_conditions": ["..."], "steps": [{"order": 1, "action": "..."}], '
        '"tags": ["..."], "confidence": 0.0-1.0}'
    )
    user_msg = f"--- Intelligence Cluster ---\n{intel_context}\n{ai_context}"

    try:
        result_text = await call_llm(
            user_msg[:6000],
            system_prompt=system_prompt,
            max_tokens=1200,
            task_type="playbook_generation",
        )
        return parse_llm_json(result_text, context="playbook_generation")
    except Exception as e:
        logger.error(f"Playbook generation LLM call failed: {e}")
        return None


async def _generate_skills_from_playbook(
    playbook_id: str,
    playbook_data: dict,
    entity_type: str,
    config: dict,
):
    """Decompose playbook steps into reusable skills."""
    steps = playbook_data.get("steps", [])
    if not steps:
        return

    system_prompt = (
        "You are a skill extractor for a CRM memory system.\n\n"
        "Given a playbook's ordered steps, identify 1-3 distinct reusable capabilities (skills) "
        "that the agent needs to execute these steps. Each skill should be a discrete, composable ability.\n\n"
        "For each skill return:\n"
        '- "name": short descriptive name\n'
        '- "skill_type": "soft" (behavioral) or "hard" (technical)\n'
        '- "trigger_desc": when to activate this skill\n'
        '- "procedure": how to execute (natural language)\n\n'
        'Return JSON array: [{"name": "...", "skill_type": "...", "trigger_desc": "...", "procedure": "..."}]'
    )
    steps_text = "\n".join(f"Step {s.get('order')}: {s.get('action')}" for s in steps)
    user_msg = f"Playbook: {playbook_data.get('name')}\n\nSteps:\n{steps_text}"

    try:
        result_text = await call_llm(
            user_msg,
            system_prompt=system_prompt,
            max_tokens=800,
            task_type="skill_generation",
        )
        skills = parse_llm_json(result_text, context="skill_generation")
        if not isinstance(skills, list):
            skills = [skills]
    except Exception as e:
        logger.error(f"Skill decomposition LLM call failed: {e}")
        return

    auto_activate = config.get("skill_auto_activate", False)
    for skill_data in skills[:5]:
        skill_id = str(uuid.uuid4())
        metadata = {
            "skill_type": skill_data.get("skill_type", "hard"),
            "trigger_desc": skill_data.get("trigger_desc", ""),
            "procedure": skill_data.get("procedure", ""),
            "entity_types": [entity_type],
            "playbook_ids": [playbook_id],
        }
        embedding_text = f"{skill_data.get('name')}. {skill_data.get('trigger_desc', '')}"
        embedding = None
        try:
            embedding = await generate_embedding(embedding_text)
        except Exception:
            pass

        # Dedup check for skill
        existing = None
        if embedding:
            existing = await find_similar_existing(embedding, 0.85, category="skill")
        if existing:
            increment_merge(existing)
            continue

        status = "active" if auto_activate else "draft"
        quality = compute_quality_score(0.5, 0.0, 0.5, 0, 0.0)
        insert_knowledge(
            knowledge_id=skill_id,
            intelligence_ids=[],
            signals=playbook_data.get("signals", []),
            category="skill",
            name=skill_data.get("name", "Unnamed Skill"),
            content=skill_data.get("procedure", ""),
            summary=skill_data.get("trigger_desc", ""),
            embedding=embedding,
            tags=playbook_data.get("tags", []),
            source_pathway="decomposed",
            extraction_confidence=0.5,
            quality_score=quality,
            status=status,
            metadata=metadata,
        )
        logger.info(f"Created skill '{skill_data.get('name')}' [{status}] from playbook {playbook_id}")


def _mark_processed(interaction_ids: list):
    """Mark AI interactions as processed by playbook extraction."""
    if not interaction_ids:
        return
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        for iid in interaction_ids:
            cursor.execute(
                "INSERT INTO playbook_processed_interactions (interaction_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (iid,)
            )
