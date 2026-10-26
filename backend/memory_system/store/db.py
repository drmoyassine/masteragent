"""
memory_system/store/db.py — PostgreSQL schema + initialization for the Memory System

Uses:
  - psycopg2 for PostgreSQL connections (via core/storage.py)
  - pgvector extension for VECTOR columns
  - gen_random_uuid() for UUIDs (requires pgcrypto)

Tables:
  Config:     memory_entity_types, memory_entity_subtypes,
              memory_channel_types, memory_agents, memory_system_prompts,
              memory_llm_configs, memory_settings, memory_entity_type_config
  Tier 0:     interactions
  Tier 1:     memories
  Tier 2:     intelligence
  Tier 3:     knowledge
  Audit:      memory_audit_log
"""
import json
import logging
import uuid
from datetime import datetime, timezone
import psycopg2

from core.storage import get_memory_db_context
from core.database import get_database_url
from core.secrets import encrypt_secret, is_encrypted
from memory_system.store.migrations import apply_pending

logger = logging.getLogger(__name__)

def _persist_index_build_alert(cursor, index_name: str, exc: Exception) -> None:
    """Sticky-alert a failed load-bearing index build.

    A failed CREATE UNIQUE INDEX CONCURRENTLY leaves an invalid placeholder
    that cannot arbitrate ON CONFLICT — every insert it serves then errors
    (2026-10-15 outage: the dedup index failed on two pre-existing duplicate
    keys and the warning-only swallow left the app serving 500s invisibly
    for ~30 min). docker logs are unreadable on the deployed panel, so the
    alerts banner is the only surface operators actually see.
    """
    try:
        cursor.execute("""
            INSERT INTO memory_system_alerts
                (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
            VALUES (%s, 'critical', 'Operational index build failed', %s,
                    'memory_system.store.db', %s::jsonb, TRUE, NOW(), NOW())
            ON CONFLICT (code) DO UPDATE SET active=TRUE, message=EXCLUDED.message,
                detail=EXCLUDED.detail, last_seen_at=NOW()
        """, (
            f"index_build_failed:{index_name}",
            f"Index {index_name} failed to build; requests relying on it will error until this is resolved.",
            json.dumps({"index": index_name, "error": f"{type(exc).__name__}: {exc}"}),
        ))
    except Exception as alert_exc:
        logger.error("Failed to persist index-build alert for %s: %s", index_name, alert_exc)

def _create_operational_indexes_concurrently():
    """Build new potentially-large indexes without blocking production writes."""
    statements = [
        ("idx_interactions_fts", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_interactions_fts ON interactions USING GIN (to_tsvector('simple', coalesce(content, '')))"),
        ("idx_memories_fts", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_fts ON memories USING GIN (to_tsvector('simple', coalesce(content_summary, '')))"),
        ("idx_intelligence_fts", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_intelligence_fts ON intelligence USING GIN (to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')))"),
        ("idx_knowledge_fts", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_knowledge_fts ON knowledge USING GIN (to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')))"),
        ("idx_interactions_entity_status_time", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_interactions_entity_status_time ON interactions (primary_entity_type, primary_entity_id, status, timestamp DESC)"),
        ("idx_intelligence_entity_status_created", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_intelligence_entity_status_created ON intelligence (primary_entity_type, primary_entity_id, status, created_at DESC)"),
        # TASK-258 (DEC-106): comm-dedup authority — n8nclaw's carrier key
        # (metadata.crm_dedup_key = comm_id|tier|itype, the webhook gate's key).
        # Partial: rows without the key (every other consumer + all legacy data)
        # are excluded, so the build stays near-empty and dedup never touches
        # them.
        ("uq_interactions_crm_dedup_key", "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_interactions_crm_dedup_key ON interactions ((COALESCE(metadata->>'crm_dedup_key', ''))) WHERE COALESCE(metadata->>'crm_dedup_key', '') <> ''"),
    ]
    conn = psycopg2.connect(get_database_url())
    conn.autocommit = True
    try:
        cursor = conn.cursor()
        for index_name, statement in statements:
            load_bearing = statement.lstrip().upper().startswith("CREATE UNIQUE")
            try:
                cursor.execute("""
                    SELECT i.indisvalid FROM pg_index i
                    JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relname=%s
                """, (index_name,))
                state = cursor.fetchone()
                if state and not state[0]:
                    cursor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
                cursor.execute(statement)
                if load_bearing:
                    cursor.execute(
                        "UPDATE memory_system_alerts SET active=FALSE WHERE code=%s AND active=TRUE",
                        (f"index_build_failed:{index_name}",),
                    )
            except Exception as exc:
                if load_bearing:
                    logger.error("Load-bearing index %s failed to build: %s", index_name, exc)
                    _persist_index_build_alert(cursor, index_name, exc)
                else:
                    logger.warning("Concurrent index migration skipped: %s", exc)
    finally:
        conn.close()

def _enable_extensions(cursor):
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

def init_memory_db():
    """TASK-257 s3: schema DDL is owned by the frozen migration ledger.

    backend/migrations/*.sql applies once each, tracked in
    schema_migrations (store.migrations) - fresh installs build from
    001_baseline; deployments that predate the freeze are stamped
    001-applied without executing it. The phase-2 cutover deleted the
    pre-freeze boot DDL (_create_* / _run_migrations); the settings-drift
    oracle reads backend/migrations/*.sql as its schema source.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        _enable_extensions(cursor)
        apply_pending(conn)

        # Operational hardening migrations are additive and safe on existing
        # production tables.
        cursor.execute("ALTER TABLE memory_job_log ADD COLUMN IF NOT EXISTS status TEXT")
        cursor.execute("ALTER TABLE memory_job_log ADD COLUMN IF NOT EXISTS last_error TEXT")
        cursor.execute("ALTER TABLE memory_job_log ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ")

        cursor.execute("""
            INSERT INTO memory_agent_entities (agent_id, entity_type, entity_id)
            SELECT DISTINCT i.agent_id, i.primary_entity_type, i.primary_entity_id
            FROM interactions i
            JOIN memory_agents a ON a.id = i.agent_id
            WHERE i.primary_entity_type IS NOT NULL AND i.primary_entity_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)

        cursor.execute("SELECT id, api_key_encrypted FROM memory_llm_providers WHERE api_key_encrypted IS NOT NULL AND api_key_encrypted <> ''")
        for row in cursor.fetchall():
            if not is_encrypted(row["api_key_encrypted"]):
                cursor.execute(
                    "UPDATE memory_llm_providers SET api_key_encrypted = %s WHERE id = %s",
                    (encrypt_secret(row["api_key_encrypted"]), row["id"]),
                )
        logger.info("Memory system database schema initialized")

    _seed_defaults()
    _create_operational_indexes_concurrently()

def _seed_defaults():
    """Seed default configuration data. Idempotent."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        # Settings singleton
        cursor.execute("""
            INSERT INTO memory_settings (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING
        """)

        # One-time compatibility migration into the unified Knowledge policy.
        cursor.execute("SELECT * FROM memory_settings WHERE id = 1")
        policy_row = cursor.fetchone()
        if policy_row and not policy_row.get("knowledge_policy_migrated", False):
            overrides = {}
            global_tokens = int(policy_row.get("knowledge_max_tokens") or 1200)
            global_conf = float(policy_row.get("extraction_confidence_threshold") or 0.60)
            global_time = policy_row.get("knowledge_generation_time") or "03:00"
            telemetry_override = {}
            if int(policy_row.get("telemetry_reflection_max_tokens") or global_tokens) != global_tokens:
                telemetry_override["max_tokens"] = int(policy_row["telemetry_reflection_max_tokens"])
            if float(policy_row.get("telemetry_reflection_confidence_min") or global_conf) != global_conf:
                telemetry_override["min_confidence"] = float(policy_row["telemetry_reflection_confidence_min"])
            if (policy_row.get("telemetry_reflection_time") or global_time) != global_time:
                telemetry_override["schedule_time"] = policy_row["telemetry_reflection_time"]
            if telemetry_override:
                overrides["telemetry_reflection"] = telemetry_override
            cursor.execute("""
                UPDATE memory_settings SET
                    knowledge_generation_max_tokens = %s,
                    knowledge_generation_min_confidence = %s,
                    knowledge_generation_time = %s,
                    knowledge_generation_evidence_threshold = COALESCE(knowledge_threshold, 5),
                    knowledge_generation_approval_policy = CASE
                        WHEN COALESCE(knowledge_auto_activate, TRUE) THEN 'approve_immediately'
                        ELSE 'create_as_draft' END,
                    knowledge_generation_pathway_overrides = %s::jsonb,
                    knowledge_policy_migrated = TRUE
                WHERE id = 1
            """, (global_tokens, global_conf, global_time, json.dumps(overrides)))
            logger.info("Migrated legacy Knowledge settings into unified generation policy")

        # Per-entity threshold migration is independent of the global settings
        # flag because entity types may be created or imported later. Preserve
        # the legacy value as a compatibility field but make the canonical
        # declarative-pathway override explicit exactly once.
        cursor.execute("""
            UPDATE memory_entity_type_config
            SET knowledge_generation_overrides = jsonb_set(
                COALESCE(knowledge_generation_overrides, '{}'::jsonb),
                '{declarative_knowledge,evidence_threshold}',
                to_jsonb(knowledge_extraction_threshold), true
            )
            WHERE knowledge_extraction_threshold IS NOT NULL
              AND COALESCE(knowledge_generation_overrides #>> '{declarative_knowledge,evidence_threshold}', '') = ''
        """)

        # ── One-time backfills (guarded by memory_settings flags; run once) ──
        # Backfill #2: activate existing draft knowledge. The new global
        # knowledge_auto_activate dial defaults True, so historical drafts (the 94
        # telemetry-reflected records) should join the active set the agent sees.
        cursor.execute("SELECT knowledge_drafts_backfilled FROM memory_settings WHERE id=1")
        _row = cursor.fetchone()
        if _row and not _row["knowledge_drafts_backfilled"]:
            cursor.execute("UPDATE knowledge SET status='active', updated_at=now() WHERE status='draft'")
            cursor.execute("UPDATE memory_settings SET knowledge_drafts_backfilled=TRUE WHERE id=1")
            logger.info("Backfill: activated existing draft knowledge records")

        # Backfill #3: lowercase existing knowledge signals so the historical casing
        # split (momentum vs Momentum) collapses into single canonical buckets.
        cursor.execute("SELECT knowledge_signals_lowercased FROM memory_settings WHERE id=1")
        _row = cursor.fetchone()
        if _row and not _row["knowledge_signals_lowercased"]:
            cursor.execute("""
                UPDATE knowledge
                SET signals = ARRAY(SELECT DISTINCT lower(x) FROM unnest(signals) AS x)
                WHERE cardinality(signals) > 0
            """)
            cursor.execute("UPDATE memory_settings SET knowledge_signals_lowercased=TRUE WHERE id=1")
            logger.info("Backfill: lowercased existing knowledge signals")

        # Entity types
        for name, icon in [("contact", "👤"), ("institution", "🏢"), ("program", "📋"), ("supplier", "🏭"), ("product", "📦")]:
            cursor.execute(
                "INSERT INTO memory_entity_types (name, icon) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                (name, icon)
            )

        # Entity subtypes
        cursor.execute("SELECT id, name FROM memory_entity_types")
        entity_type_map = {row["name"]: row["id"] for row in cursor.fetchall()}

        contact_subtypes = ["lead", "client", "partner", "supplier", "internal", "other"]
        for subtype in contact_subtypes:
            if "contact" in entity_type_map:
                cursor.execute(
                    "INSERT INTO memory_entity_subtypes (entity_type_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (entity_type_map["contact"], subtype)
                )

        institution_subtypes = ["client", "partner", "supplier", "school", "internal", "other"]
        for subtype in institution_subtypes:
            if "institution" in entity_type_map:
                cursor.execute(
                    "INSERT INTO memory_entity_subtypes (entity_type_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (entity_type_map["institution"], subtype)
                )

        # Channel types (kept for backwards compat with interaction_type display)
        for name, icon in [
            ("email_sent", "📧"), ("email_received", "📨"), ("call", "📞"),
            ("meeting", "🤝"), ("whatsapp", "💬"), ("crm_note", "📝"),
            ("document", "📄"), ("ai_conversation", "🤖"), ("webhook_event", "🔗")
        ]:
            cursor.execute(
                "INSERT INTO memory_channel_types (name, icon) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                (name, icon)
            )

        # Default LLM Providers (only seed if table is completely empty)
        cursor.execute("SELECT COUNT(*) as cnt FROM memory_llm_providers")
        if cursor.fetchone()["cnt"] == 0:
            default_providers = {
                "openai": ("Default OpenAI", "openai", ""),
                "gliner": ("Local GLiNER", "gliner", "http://gliner:8002"),
                "zendata": ("Zendata PII", "zendata", "")
            }

            for p_key, (p_name, p_type, base_url) in default_providers.items():
                cursor.execute("""
                    INSERT INTO memory_llm_providers (name, provider, api_base_url)
                    SELECT %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM memory_llm_providers WHERE name = %s
                    )
                """, (p_name, p_type, base_url, p_name))

        # Default LLM configs structured logically into pipelines (only seed if table is empty)
        cursor.execute("SELECT COUNT(*) as cnt FROM memory_llm_configs")
        if cursor.fetchone()["cnt"] == 0:
            for task_type, provider_key, model, pipeline_stage, exec_order, prompt, schema in [
                ("vision", "openai", "gpt-4o", "interactions", 0,
                 "Extract all text content from this document. Include all readable text, table contents (as markdown tables), and important visual information in [brackets]. Output clean markdown without conversational filler.",
                 ""),
                ("entity_extraction", "gliner", "urchade/gliner_multi", "memories", 0,
                 "Extract named entities from the text. Focus only on these types: {{labels}}.\nReturn a JSON array: [{\"entity_id\": \"uuid\", \"entity_type\": \"...\", \"name\": \"...\", \"role\": \"...\"}]",
                 ""),
                ("embedding", "openai", "text-embedding-3-small", "memories", 1, "", ""),
                ("memory_generation", "openai", "gpt-4o-mini", "memories", 2,
                 "You are an AI memory system. Based on the provided interaction data, write a concise factual memory record.\n\nINTERACTION TYPES (voice attribution):\n- incoming_whatsapp_message — the contact's own words\n- outgoing_whatsapp_message — the AI's reply (not the contact)\n- internal_note / crm_note_inserted — a human counselor's note about the contact\n- internal_ai_thought / internal_ai_tool_call — agent telemetry, NOT the contact's words\n\nPRIOR CONTEXT RULES:\n- Previous memories for this entity are provided under 'Prior Context'.\n- These represent ESTABLISHED facts. Do NOT repeat them.\n- Focus EXCLUSIVELY on NEW information from today's interactions.\n- Note any progressions, status changes, or contradictions with prior records.\n- If today's interactions contain no new information beyond prior context, write a brief note stating the interaction occurred with no significant new details.\n\nOUTPUT RULES:\n- Return only the summary text, 2-5 sentences.\n- Focus on key facts, decisions, named entities, and action items.",
                 ""),
                ("intelligence_generation", "openai", "gpt-4o-mini", "intelligence", 0,
                 "You are a deal intelligence analyst reviewing interaction history for {{ entity.type }} / {{ entity.id }}.\n\nYour job is not to summarize — surface what the memories reveal beneath the surface.\n\nProbe the memories against these intelligence signals:\n\n{{ intelligence_signals }}\n\nFor each signal with evidence, note the evidence and its strength. Return JSON: {\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\"}. knowledge_type must be one of: behavior_pattern, risk_signal, opportunity, relationship_shift, preference, milestone.",
                 ""),
                ("pii_scrubbing", "zendata", "", "knowledge", 0, "", ""),
                ("knowledge_generation", "openai", "gpt-4o-mini", "knowledge", 1,
                 "You are a knowledge curator for an agent harness. The input is de-identified intelligence from multiple interactions. Produce one durable, reusable Knowledge item only when the sources support it; otherwise return a no_candidate decision. Remove specific names and never invent facts, deadlines, qualifications, jurisdictions, or facet values. Preserve conditions, exceptions, causal context, scope, and unresolved contradictions. Never turn separate incidents into one fabricated lesson.\n\nFocus on these knowledge signals:\n\n{{ knowledge_signals }}\n\nReturn ONLY JSON with schema_version='knowledge-generation-v2', decision ('create'|'no_candidate'), name, category, summary, content, signals, tags, facets, confidence, qualifications, contradictions, source_support. category must be one of best_practices, lessons_learned, trade_knowledge. For best_practices preserve recommendations, conditions and exceptions. For lessons_learned preserve causal context and incident distinctions. For trade_knowledge preserve jurisdiction, institution, product, intake, and environmental distinctions when explicitly supported.",
                 ""),
                 ("summarization", "openai", "gpt-4o-mini", "intelligence", -1,
                 "Summarize this in 1-2 sentences:\n\n{{text}}",
                 ""),
            ]:
                cursor.execute("""
                    INSERT INTO memory_llm_configs (task_type, provider_id, model_name, is_active, pipeline_stage, execution_order, inline_system_prompt, inline_schema)
                    SELECT %s, (SELECT id FROM memory_llm_providers WHERE provider = %s LIMIT 1), %s, TRUE, %s, %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM memory_llm_configs WHERE pipeline_stage = %s AND task_type = %s
                    )
                """, (task_type, provider_key, model, pipeline_stage, exec_order, prompt, schema, pipeline_stage, task_type))

                # Migrate existing configs that may have been created before inline_system_prompt was seeded
                cursor.execute("""
                    UPDATE memory_llm_configs
                    SET inline_system_prompt = %s, inline_schema = %s
                    WHERE task_type = %s AND (inline_system_prompt IS NULL OR inline_system_prompt = '')
                """, (prompt, schema, task_type))

        # Hotfix: Ensure summarization is properly mapped to intelligence for migrating existing users
        # Only move it if it's still on 'interactions' (one-time migration)
        cursor.execute("""
            UPDATE memory_llm_configs
            SET pipeline_stage = 'intelligence'
            WHERE task_type = 'summarization' AND pipeline_stage = 'interactions'
        """)

        # Knowledge-stage generation nodes that pick-by-task_type (NOT a sequential
        # pipeline). Their prompts are admin-editable via inline_system_prompt, seeded
        # from the canonical constants in the implementation modules (single source of
        # truth). Seeded for EXISTING installs too (idempotent), attached to the same
        # provider/model as knowledge_generation when available.
        try:
            from memory_system.distill.skills import _SKILL_GEN_PROMPT
            from memory_system.distill.telemetry import _REFLECTION_SYSTEM_PROMPT
            pick_nodes = [
                ("skill_generation", 3, _SKILL_GEN_PROMPT),
                ("telemetry_reflection", 4, _REFLECTION_SYSTEM_PROMPT),
            ]
        except Exception as e:
            logger.warning(f"Could not import generation prompt constants for seeding: {e}")
            pick_nodes = [
                ("skill_generation", 3, ""), ("telemetry_reflection", 4, ""),
            ]

        for pb_task, pb_order, pb_prompt in pick_nodes:
            cursor.execute("""
                INSERT INTO memory_llm_configs
                    (task_type, provider_id, model_name, is_active, pipeline_stage, execution_order, inline_system_prompt, inline_schema)
                SELECT %s,
                       COALESCE(
                           (SELECT provider_id FROM memory_llm_configs WHERE task_type = 'knowledge_generation' AND is_active = TRUE LIMIT 1),
                           (SELECT id FROM memory_llm_providers WHERE provider = 'openai' LIMIT 1)
                       ),
                       COALESCE(
                           (SELECT model_name FROM memory_llm_configs WHERE task_type = 'knowledge_generation' AND is_active = TRUE LIMIT 1),
                           'gpt-4o-mini'
                       ),
                       TRUE, 'knowledge', %s, %s, ''
                WHERE NOT EXISTS (
                    SELECT 1 FROM memory_llm_configs WHERE task_type = %s
                )
            """, (pb_task, pb_order, pb_prompt, pb_task))
            # Backfill the prompt for existing installs where the node exists but is empty
            if pb_prompt:
                cursor.execute("""
                    UPDATE memory_llm_configs
                    SET inline_system_prompt = %s
                    WHERE task_type = %s AND (inline_system_prompt IS NULL OR inline_system_prompt = '')
                """, (pb_prompt, pb_task))

        # Knowledge consolidation LLM config — same provider/model as
        # knowledge_generation (credentials are NOT copied; resolved via the
        # shared provider row). Powers the category-aware consolidation proposal.
        try:
            from memory_system.maintain.consolidation_prompts import CONSOLIDATION_BASE_PROMPT
        except Exception:
            CONSOLIDATION_BASE_PROMPT = ""
        cursor.execute("""
            INSERT INTO memory_llm_configs
                (task_type, provider_id, model_name, is_active, pipeline_stage, execution_order, inline_system_prompt, inline_schema)
            SELECT 'knowledge_consolidation',
                   COALESCE(
                       (SELECT provider_id FROM memory_llm_configs WHERE task_type = 'knowledge_generation' AND is_active = TRUE LIMIT 1),
                       (SELECT id FROM memory_llm_providers WHERE provider = 'openai' LIMIT 1)
                   ),
                   COALESCE(
                       (SELECT model_name FROM memory_llm_configs WHERE task_type = 'knowledge_generation' AND is_active = TRUE LIMIT 1),
                       'gpt-4o-mini'
                   ),
                   TRUE, 'knowledge', 5, %s, ''
            WHERE NOT EXISTS (
                SELECT 1 FROM memory_llm_configs WHERE task_type = 'knowledge_consolidation'
            )
        """, (CONSOLIDATION_BASE_PROMPT,))
        if CONSOLIDATION_BASE_PROMPT:
            cursor.execute("""
                UPDATE memory_llm_configs
                SET inline_system_prompt = %s
                WHERE task_type = 'knowledge_consolidation' AND (inline_system_prompt IS NULL OR inline_system_prompt = '')
            """, (CONSOLIDATION_BASE_PROMPT,))

        # Default system prompts
        prompts = [
            ("memory_generation", "Default Memory Generator",
             "You are an AI memory system. Based on the provided interaction data, write a concise "
             "factual memory record. Focus on key facts, decisions, named entities, and action items. "
             "Return only the summary text, 2-5 sentences."),
            ("summarization", "Default Summarizer",
             "You are a concise summarizer. Summarize the following interaction in 2-3 sentences, "
             "focusing on key facts, decisions, and action items. Be factual and brief."),
            ("intelligence_generation", "Default Insight Generator",
             "You are an AI analyst reviewing interaction history for a specific entity. "
             "Based on the provided memory summaries, identify 1 to 3 distinct, meaningful signals. "
             "Return a JSON array only (even for a single result): "
             "[{\"name\": \"...\", \"signals\": [\"...\"], \"content\": \"...\", \"summary\": \"...\"}]. "
             "Set \"signals\" to one or more of the defined signal names provided to you for this entity type. "
             "Only include signals genuinely supported by the data."),
            ("entity_extraction", "Default Entity Extractor",
             "Extract named entities from the following text. Return a JSON array of objects: "
             "[{\"entity_id\": \"unique-id\", \"entity_type\": \"contact|institution|program|supplier|product\", "
             "\"name\": \"...\", \"role\": \"...\"}]. Only include clearly identifiable entities."),
            ("entity_workspace", "Default Entity Workspace Assistant",
             "You are an intelligent assistant helping manage a relationship with a specific entity. "
             "You have access to the entity's interaction history as memory summaries, extracted intelligence, "
             "and general knowledge. Use this context to give personalized, factual answers. "
             "If you identify a new pattern or important observation, you may create an insight using the action syntax."),
        ]
        for prompt_type, name, text in prompts:
            cursor.execute("""
                INSERT INTO memory_system_prompts (prompt_type, name, prompt_text, is_active)
                SELECT %s, %s, %s, TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM memory_system_prompts WHERE prompt_type = %s
                )
            """, (prompt_type, name, text, prompt_type))

        # Backfill inline prompts and schemas for the UI if they are null
        # We do this so the Accordion UI fields are not empty by default for new/existing setups
        for prompt_type, name, text in prompts:
            if prompt_type in ["memory_generation", "summarization", "intelligence_generation", "entity_extraction", "pii_scrubbing"]:
                cursor.execute("""
                    UPDATE memory_llm_configs
                    SET inline_system_prompt = %s
                    WHERE task_type = %s AND inline_system_prompt IS NULL
                """, (text, prompt_type))

        # Add default GLiNER schema to entity_extraction config if null
        cursor.execute("""
            UPDATE memory_llm_configs
            SET inline_schema = %s
            WHERE task_type = 'entity_extraction' AND inline_schema IS NULL
        """, ('{\n  "entities": ["Organization", "Person", "Location", "Product", "Event"]\n}',))

        # Add intelligence default schema
        cursor.execute("""
            UPDATE memory_llm_configs
            SET inline_schema = %s
            WHERE task_type = 'intelligence_generation' AND inline_schema IS NULL
        """, ('[\n  {\n    "name": "...",\n    "signals": ["..."],\n    "content": "...",\n    "summary": "..."\n  }\n]',))

        # Default entity type configs
        for entity_type in ["contact", "institution", "program", "supplier", "product"]:
            cursor.execute("""
                INSERT INTO memory_entity_type_config (entity_type)
                VALUES (%s)
                ON CONFLICT (entity_type) DO NOTHING
            """, (entity_type,))

        # Default knowledge signals per entity type (only applied when column is still NULL)
        _DEFAULT_KNOWLEDGE_SIGNALS = {
            "contact": [
                {
                    "name": "Conversion & Closing Patterns",
                    "description": "Recurring sequences of touchpoints that led to commitment, "
                        "common triggers that moved contacts from consideration to decision, "
                        "timing patterns across the sales or enrollment funnel",
                },
                {
                    "name": "Objection & Resolution Repertoire",
                    "description": "Frequently surfacing objections by contact segment or profile, "
                        "counter-arguments or reframings that resolved hesitation, "
                        "objections that consistently killed deals and why",
                },
                {
                    "name": "Relationship & Trust Signals",
                    "description": "Communication styles and frequencies that built rapport, "
                        "influencer dynamics (parents, advisors, peers) affecting decisions, "
                        "trust-eroding events and how they were recovered",
                },
                {
                    "name": "Segment Behavioral Patterns",
                    "description": "Decision-making tendencies shared across a contact type or demographic, "
                        "information needs at each stage, "
                        "urgency or delay patterns tied to season, budget cycle, or life event",
                },
                {
                    "name": "Customer Service Resolution Patterns",
                    "description": "Issue types that recur across contacts and how they were resolved, "
                        "escalation triggers and de-escalation tactics, "
                        "service failures that drove churn and preventable patterns",
                },
            ],
            "institution": [
                {
                    "name": "Partnership Value & Fit Signals",
                    "description": "Institution traits (ranking, location, flexibility) that correlate with "
                        "high student satisfaction or placement success, "
                        "red flags in institutional behavior that predict problems",
                },
                {
                    "name": "Negotiation & Capacity Dynamics",
                    "description": "Pricing flexibility patterns, minimum cohort requirements, "
                        "timeline rigidity vs. accommodation history, "
                        "how institutions respond to non-standard requests",
                },
                {
                    "name": "Reputation & Trust Indicators",
                    "description": "Signals that built or eroded institutional trust over time, "
                        "consistency between what institutions promise and deliver, "
                        "staff relationship patterns that affect outcomes",
                },
                {
                    "name": "Competitive Positioning Insights",
                    "description": "How this institution is perceived versus alternatives by student segment, "
                        "unique strengths consistently cited in decisions, "
                        "weaknesses that cause it to lose placements to competitors",
                },
            ],
            "program": [
                {
                    "name": "Demand & Fit Patterns",
                    "description": "Student segments most attracted to this program type and why, "
                        "program features that are deal-makers vs. nice-to-haves, "
                        "mismatches between student expectations and program reality",
                },
                {
                    "name": "Conversion & Drop-off Points",
                    "description": "Stages where student interest consistently peaks or dies, "
                        "information or experiences that convert interest to enrollment, "
                        "common drop-off reasons and whether they are addressable",
                },
                {
                    "name": "Competitive Differentiation",
                    "description": "What distinguishes high-performing programs from alternatives, "
                        "positioning language that resonates with each student segment, "
                        "pricing and value framing that overcomes cost objections",
                },
                {
                    "name": "Outcome & Satisfaction Drivers",
                    "description": "Program elements most cited in positive post-experience feedback, "
                        "recurring dissatisfiers and whether they are systemic, "
                        "outcomes (career, academic, personal) that motivate referrals",
                },
            ],
            "supplier": [
                {
                    "name": "Reliability & Service Quality Patterns",
                    "description": "Recurring signals that predict supplier reliability or risk, "
                        "service failure types and how quickly they were resolved, "
                        "consistency between quoted and delivered quality",
                },
                {
                    "name": "Cost-Value & Negotiation Dynamics",
                    "description": "Where supplier pricing aligns or misaligns with student outcomes, "
                        "flexibility shown on pricing, scope, or deadlines across engagements, "
                        "hidden costs or value-adds that recur",
                },
                {
                    "name": "Relationship Health Indicators",
                    "description": "Communication patterns that indicate a strong vs. strained partnership, "
                        "supplier behaviors that signal growing or shrinking commitment, "
                        "escalation paths and resolution effectiveness",
                },
            ],
            "product": [
                {
                    "name": "Demand Drivers & Positioning",
                    "description": "Features or conditions that consistently increase product uptake, "
                        "messaging frames that resonate with specific buyer segments, "
                        "seasonal or lifecycle timing that influences demand",
                },
                {
                    "name": "Objection & Barrier Patterns",
                    "description": "Recurring objections by buyer type and effective responses, "
                        "pricing sensitivities and how discounting affected close rates, "
                        "competitor alternatives that come up most and how they were countered",
                },
                {
                    "name": "Upsell & Cross-sell Signals",
                    "description": "Product combinations that consistently appear in high-value deals, "
                        "timing signals that indicate readiness for an upgrade or add-on, "
                        "buyer profiles that over-index for expansion revenue",
                },
            ],
        }

        for entity_type, signals in _DEFAULT_KNOWLEDGE_SIGNALS.items():
            cursor.execute("""
                UPDATE memory_entity_type_config
                SET knowledge_signals_prompt = %s
                WHERE entity_type = %s
                  AND knowledge_signals_prompt IS NULL
            """, (json.dumps(signals), entity_type))

        # Sprint 2.5 — seed global facets schema + always-on Knowledge Management
        # skill. Inside this transaction: the seeders must adopt our cursor —
        # their own connection would self-deadlock on our uncommitted
        # memory_settings row (found by the 2026-10-15 boot smoke).
        try:
            from memory_system.distill.facets import seed_default_facets_schema, seed_management_skill
            seed_default_facets_schema(cursor)
            seed_management_skill(cursor)
        except Exception as e:
            logger.warning(f"Sprint 2.5 seeding skipped: {e}")

        logger.info("Memory system defaults seeded")

