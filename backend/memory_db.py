"""
memory_db.py — PostgreSQL schema + initialization for the Memory System

Uses:
  - psycopg2 for PostgreSQL connections (via core/storage.py)
  - pgvector extension for VECTOR columns
  - gen_random_uuid() for UUIDs (requires pgcrypto)

Tables:
  Config:     memory_entity_types, memory_entity_subtypes, memory_lesson_types,
              memory_channel_types, memory_agents, memory_system_prompts,
              memory_llm_configs, memory_settings, memory_entity_type_config
  Tier 0:     interactions
  Tier 1:     memories
  Tier 2:     insights
  Tier 3:     lessons
  Audit:      memory_audit_log
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


def init_memory_db():
    """Initialize all memory system tables in PostgreSQL. Idempotent."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        # Enable required extensions
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

        # ── Configuration Tables ─────────────────────────────────────────────

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entity_types (
                id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                name        TEXT NOT NULL UNIQUE,
                icon        TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entity_subtypes (
                id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                entity_type_id  TEXT NOT NULL REFERENCES memory_entity_types(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (entity_type_id, name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_lesson_types (
                id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                name        TEXT NOT NULL UNIQUE,
                color       TEXT DEFAULT '#6B7280',
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_channel_types (
                id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                name        TEXT NOT NULL UNIQUE,
                description TEXT,
                icon        TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Idempotent migrations: add description to all config types tables
        for tbl in ["memory_entity_types", "memory_entity_subtypes",
                    "memory_lesson_types", "memory_channel_types"]:
            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS description TEXT")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_agents (
                id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                name            TEXT NOT NULL,
                description     TEXT,
                api_key_hash    TEXT NOT NULL UNIQUE,
                api_key_preview TEXT,
                access_level    TEXT DEFAULT 'standard',
                is_active       BOOLEAN DEFAULT TRUE,
                last_used       TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Idempotent migration: add all potentially missing columns to memory_agents
        for col, col_def in [
            ("name", "TEXT NOT NULL DEFAULT ''"),
            ("description", "TEXT"),
            ("api_key_hash", "TEXT UNIQUE"),
            ("api_key_preview", "TEXT DEFAULT ''"),
            ("access_level", "TEXT DEFAULT 'private'"),
            ("last_used", "TIMESTAMPTZ"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE memory_agents ADD COLUMN IF NOT EXISTS {col} {col_def}")
            except Exception:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_system_prompts (
                id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                prompt_type TEXT NOT NULL,
                name        TEXT NOT NULL,
                prompt_text TEXT NOT NULL,
                is_active   BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_llm_configs (
                id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                task_type           TEXT NOT NULL,
                provider            TEXT NOT NULL,
                name                TEXT NOT NULL DEFAULT '',
                api_base_url        TEXT,
                api_key_encrypted   TEXT,
                api_key_preview     TEXT DEFAULT '',
                model_name          TEXT,
                extra_config_json   TEXT DEFAULT '{}',
                is_active           BOOLEAN DEFAULT TRUE,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Partial unique index: only one active config per task_type
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_configs_active_task
            ON memory_llm_configs (task_type) WHERE is_active = TRUE
        """)
        # Idempotent migrations: add columns if missing from older schema
        for col, col_def in [
            ("name", "TEXT NOT NULL DEFAULT ''"),
            ("api_key_preview", "TEXT DEFAULT ''"),
            ("extra_config_json", "TEXT DEFAULT '{}'"),
        ]:
            cursor.execute(f"ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS {col} {col_def}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_settings (
                id                      INT PRIMARY KEY CHECK (id = 1),
                chunk_size              INT DEFAULT 400,
                chunk_overlap           INT DEFAULT 80,
                pii_scrubbing_enabled   BOOLEAN DEFAULT FALSE,
                auto_lesson_enabled     BOOLEAN DEFAULT TRUE,
                auto_lesson_threshold   INT DEFAULT 5,
                rate_limit_enabled      BOOLEAN DEFAULT TRUE,
                rate_limit_per_minute   INT DEFAULT 60,
                supabase_url            TEXT,
                supabase_db_url         TEXT,
                supabase_connected      BOOLEAN DEFAULT FALSE,
                updated_at              TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Idempotent migrations for existing installations
        for col, col_def in [
            ("supabase_db_url", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS {col} {col_def}")
            except Exception:
                pass



        # Per-entity-type configuration (compaction thresholds, NER, embedding)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entity_type_config (
                entity_type                 TEXT PRIMARY KEY,
                compaction_threshold        INT DEFAULT 10,
                insight_auto_approve        BOOLEAN DEFAULT FALSE,
                lesson_auto_promote         BOOLEAN DEFAULT FALSE,
                ner_enabled                 BOOLEAN DEFAULT TRUE,
                ner_confidence_threshold    FLOAT DEFAULT 0.5,
                embedding_enabled           BOOLEAN DEFAULT TRUE,
                pii_scrub_lessons           BOOLEAN DEFAULT TRUE,
                metadata_field_map          JSONB DEFAULT '{}',
                updated_at                  TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # ── Tier 0: Interactions (raw events, immutable log) ─────────────────

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id                      TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                timestamp               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                interaction_type        TEXT NOT NULL,
                agent_id                TEXT,
                agent_name              TEXT,
                content                 TEXT NOT NULL,
                primary_entity_type     TEXT NOT NULL,
                primary_entity_subtype  TEXT,
                primary_entity_id       TEXT NOT NULL,
                metadata                JSONB DEFAULT '{}',
                metadata_field_map      JSONB DEFAULT '{}',
                has_attachments         BOOLEAN DEFAULT FALSE,
                attachment_refs         JSONB DEFAULT '[]',
                source                  TEXT DEFAULT 'api',
                status                  TEXT DEFAULT 'pending',
                created_at              TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_entity ON interactions (primary_entity_type, primary_entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions (timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_status ON interactions (status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_agent ON interactions (agent_id)")

        # ── Tier 1: Memories (daily logs, NER-enriched, embedded) ────────────

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                date                DATE NOT NULL,
                primary_entity_type TEXT NOT NULL,
                primary_entity_id   TEXT NOT NULL,
                interaction_ids     TEXT[] NOT NULL DEFAULT '{}',
                interaction_count   INT NOT NULL DEFAULT 0,
                content_summary     TEXT,
                related_entities    JSONB DEFAULT '[]',
                intents             TEXT[] DEFAULT '{}',
                relationships       JSONB DEFAULT '[]',
                embedding           vector(1536),
                compaction_count    INT DEFAULT 0,
                compacted           BOOLEAN DEFAULT FALSE,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (date, primary_entity_type, primary_entity_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_entity ON memories (primary_entity_type, primary_entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_date ON memories (date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_uncompacted ON memories (primary_entity_id) WHERE compacted = FALSE")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops)")

        # Idempotent migrations: add columns missing from older memories schema
        for col, col_def in [
            ("updated_at", "TIMESTAMPTZ DEFAULT NOW()"),
            ("compacted_at", "TIMESTAMPTZ"),
        ]:
            cursor.execute(f"ALTER TABLE memories ADD COLUMN IF NOT EXISTS {col} {col_def}")

        # ── Tier 2: Insights (private, LLM-compacted patterns) ───────────────

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insights (
                id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                primary_entity_type TEXT NOT NULL,
                primary_entity_id   TEXT NOT NULL,
                source_memory_ids   TEXT[] NOT NULL DEFAULT '{}',
                insight_type        TEXT,
                name                TEXT NOT NULL,
                content             TEXT NOT NULL,
                summary             TEXT,
                embedding           vector(1536),
                status              TEXT DEFAULT 'draft',
                created_by          TEXT DEFAULT 'auto',
                confirmed_by        TEXT,
                confirmed_at        TIMESTAMPTZ,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_entity ON insights (primary_entity_type, primary_entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_status ON insights (status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_embedding ON insights USING hnsw (embedding vector_cosine_ops)")

        # ── Tier 3: Lessons (PII-scrubbed, shareable) ────────────────────────

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                source_insight_ids  TEXT[] NOT NULL DEFAULT '{}',
                lesson_type         TEXT,
                name                TEXT NOT NULL,
                content             TEXT NOT NULL,
                summary             TEXT,
                embedding           vector(1536),
                visibility          TEXT DEFAULT 'shared',
                tags                TEXT[] DEFAULT '{}',
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lessons_type ON lessons (lesson_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lessons_embedding ON lessons USING hnsw (embedding vector_cosine_ops)")

        # ── Audit Log ─────────────────────────────────────────────────────────

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_audit_log (
                id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                agent_id        TEXT,
                action          TEXT NOT NULL,
                resource_type   TEXT,
                resource_id     TEXT,
                details         JSONB DEFAULT '{}',
                timestamp       TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent ON memory_audit_log (agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON memory_audit_log (timestamp)")

        # ── Webhook Sources ────────────────────────────────────────────────────

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_webhook_sources (
                id                          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                name                        TEXT NOT NULL,
                source_system               TEXT NOT NULL,
                secret_hash                 TEXT NOT NULL,
                event_types                 TEXT[] DEFAULT '{}',
                metadata_field_map          JSONB DEFAULT '{}',
                default_interaction_type    TEXT DEFAULT 'webhook_event',
                default_entity_type         TEXT DEFAULT 'contact',
                is_active                   BOOLEAN DEFAULT TRUE,
                created_at                  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_sources_active ON memory_webhook_sources (is_active)")

        logger.info("Memory system database schema initialized")


    _seed_defaults()


def _seed_defaults():
    """Seed default configuration data. Idempotent."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        # Settings singleton
        cursor.execute("""
            INSERT INTO memory_settings (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING
        """)

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

        # Lesson types
        for name, color in [
            ("process", "#22C55E"), ("risk", "#EF4444"), ("sales", "#3B82F6"),
            ("product", "#8B5CF6"), ("support", "#F59E0B"), ("other", "#6B7280")
        ]:
            cursor.execute(
                "INSERT INTO memory_lesson_types (name, color) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                (name, color)
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

        # Default LLM configs (placeholders — user must add API keys)
        for task_type, provider, model in [
            ("summarization", "openai", "gpt-4o-mini"),
            ("embedding", "openai", "text-embedding-3-small"),
            ("vision", "openai", "gpt-4o"),
            ("entity_extraction", "gliner", "urchade/gliner_multi"),
            ("pii_scrubbing", "zendata", ""),
            ("insight_generation", "openai", "gpt-4o-mini"),
        ]:
            cursor.execute("""
                INSERT INTO memory_llm_configs (task_type, provider, model_name, is_active)
                SELECT %s, %s, %s, TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM memory_llm_configs WHERE task_type = %s AND is_active = TRUE
                )
            """, (task_type, provider, model, task_type))

        # Default system prompts
        prompts = [
            ("summarization", "Default Summarizer",
             "You are a concise summarizer. Summarize the following interaction in 2-3 sentences, "
             "focusing on key facts, decisions, and action items. Be factual and brief."),
            ("insight_generation", "Default Insight Generator",
             "You are an AI analyst reviewing interaction history for a specific entity. "
             "Based on the provided memory summaries, identify a meaningful pattern, risk, opportunity, "
             "or behavioral insight. Return JSON: {\"name\": \"...\", \"insight_type\": \"...\", "
             "\"content\": \"...\", \"summary\": \"...\"}. "
             "insight_type must be one of: behavior_pattern, risk_signal, opportunity, relationship_shift, preference, milestone."),
            ("entity_extraction", "Default Entity Extractor",
             "Extract named entities from the following text. Return a JSON array of objects: "
             "[{\"entity_id\": \"unique-id\", \"entity_type\": \"contact|institution|program|supplier|product\", "
             "\"name\": \"...\", \"role\": \"...\"}]. Only include clearly identifiable entities."),
            ("entity_workspace", "Default Entity Workspace Assistant",
             "You are an intelligent assistant helping manage a relationship with a specific entity. "
             "You have access to the entity's interaction history as memory summaries, extracted insights, "
             "and general lessons. Use this context to give personalized, factual answers. "
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

        # Default entity type configs
        for entity_type in ["contact", "institution", "program", "supplier", "product"]:
            cursor.execute("""
                INSERT INTO memory_entity_type_config (entity_type)
                VALUES (%s)
                ON CONFLICT (entity_type) DO NOTHING
            """, (entity_type,))

        logger.info("Memory system defaults seeded")
