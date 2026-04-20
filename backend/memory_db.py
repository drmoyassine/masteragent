"""
memory_db.py — PostgreSQL schema + initialization for the Memory System

Uses:
  - psycopg2 for PostgreSQL connections (via core/storage.py)
  - pgvector extension for VECTOR columns
  - gen_random_uuid() for UUIDs (requires pgcrypto)

Tables:
  Config:     memory_entity_types, memory_entity_subtypes, memory_knowledge_types,
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

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


def _enable_extensions(cursor):
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def _create_config_tables(cursor):
    """Tier 0-pre: lookup/config tables (entity types, agents, LLM configs, settings)."""
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
        CREATE TABLE IF NOT EXISTS memory_knowledge_types (
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
        CREATE TABLE IF NOT EXISTS memory_llm_providers (
            id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name                TEXT NOT NULL,
            provider            TEXT NOT NULL,
            api_base_url        TEXT,
            api_key_encrypted   TEXT,
            api_key_preview     TEXT DEFAULT '',
            rate_limit_rpm      INT DEFAULT 60,
            max_retries         INT DEFAULT 3,
            retry_delay_ms      INT DEFAULT 1000,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_llm_configs (
            id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            task_type           TEXT NOT NULL,
            pipeline_stage      TEXT,
            execution_order     INT DEFAULT 0,
            provider_id         TEXT REFERENCES memory_llm_providers(id) ON DELETE SET NULL,
            model_name          TEXT,
            prompt_id           TEXT,
            inline_system_prompt TEXT,
            inline_schema       TEXT,
            extra_config_json   TEXT DEFAULT '{}',
            is_active           BOOLEAN DEFAULT TRUE,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    # Legacy index removed to support multiple nodes per pipeline
    cursor.execute("DROP INDEX IF EXISTS idx_llm_configs_active_task")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_settings (
            id                          INT PRIMARY KEY CHECK (id = 1),
            chunk_size                  INT DEFAULT 400,
            chunk_overlap               INT DEFAULT 80,
            pii_scrubbing_enabled       BOOLEAN DEFAULT FALSE,
            auto_knowledge_enabled      BOOLEAN DEFAULT TRUE,
            auto_knowledge_threshold    INT DEFAULT 5,
            rate_limit_enabled          BOOLEAN DEFAULT TRUE,
            rate_limit_per_minute       INT DEFAULT 60,
            supabase_url                TEXT,
            supabase_db_url             TEXT,
            supabase_connected          BOOLEAN DEFAULT FALSE,
            memory_generation_time      TEXT DEFAULT '02:00',
            memory_generation_mode      TEXT DEFAULT 'ner_and_raw',
            knowledge_threshold            INT DEFAULT 5,
            intelligence_extraction_threshold INT DEFAULT 10,
            updated_at                  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_entity_type_config (
            entity_type                 TEXT PRIMARY KEY,
            intelligence_extraction_threshold INT DEFAULT 10,
            intelligence_auto_approve        BOOLEAN DEFAULT FALSE,
            knowledge_auto_promote         BOOLEAN DEFAULT FALSE,
            ner_enabled                 BOOLEAN DEFAULT TRUE,
            ner_confidence_threshold    FLOAT DEFAULT 0.5,
            ner_schema                  JSONB DEFAULT NULL,
            knowledge_extraction_threshold   INT DEFAULT NULL,
            embedding_enabled           BOOLEAN DEFAULT TRUE,
            pii_scrub_knowledge           BOOLEAN DEFAULT TRUE,
            metadata_field_map          JSONB DEFAULT '{}',
            updated_at                  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_job_log (
            job_name    TEXT PRIMARY KEY,
            last_run    TIMESTAMPTZ,
            last_date   DATE
        )
    """)


def _create_interaction_tables(cursor):
    """Tier 0: raw interaction events (immutable log)."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id                      TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            seq_id                  BIGSERIAL,
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
            embedding               vector,
            processing_errors       JSONB DEFAULT '{}',
            source                  TEXT DEFAULT 'api',
            status                  TEXT DEFAULT 'pending',
            created_at              TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_entity ON interactions (primary_entity_type, primary_entity_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions (timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_status ON interactions (status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_agent ON interactions (agent_id)")


def _create_memory_tier_tables(cursor):
    """Tiers 1-3 + audit + webhooks: memories, intelligence, knowledge, audit_log, webhook_sources."""
    # Tier 1 — daily memory logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            seq_id              BIGSERIAL,
            date                DATE NOT NULL,
            primary_entity_type TEXT NOT NULL,
            primary_entity_id   TEXT NOT NULL,
            interaction_ids     TEXT[] NOT NULL DEFAULT '{}',
            interaction_count   INT NOT NULL DEFAULT 0,
            content_summary     TEXT,
            related_entities    JSONB DEFAULT '[]',
            intents             TEXT[] DEFAULT '{}',
            relationships       JSONB DEFAULT '[]',
            embedding           vector,
            compaction_count    INT DEFAULT 0,
            compacted           BOOLEAN DEFAULT FALSE,
            processing_errors   JSONB DEFAULT '{}',
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (date, primary_entity_type, primary_entity_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_entity ON memories (primary_entity_type, primary_entity_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_date ON memories (date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_uncompacted ON memories (primary_entity_id) WHERE compacted = FALSE")
    # vector indexing omitted to support flexible embedding sizes:
    # cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops)")

    # Tier 2 — LLM-compacted intelligence
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS intelligence (
            id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            seq_id              BIGSERIAL,
            primary_entity_type TEXT NOT NULL,
            primary_entity_id   TEXT NOT NULL,
            source_memory_ids   TEXT[] NOT NULL DEFAULT '{}',
            knowledge_type        TEXT,
            name                TEXT NOT NULL,
            content             TEXT NOT NULL,
            summary             TEXT,
            embedding           vector,
            status              TEXT DEFAULT 'draft',
            created_by          TEXT DEFAULT 'auto',
            confirmed_by        TEXT,
            confirmed_at        TIMESTAMPTZ,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_intelligence_entity ON intelligence (primary_entity_type, primary_entity_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_intelligence_status ON intelligence (status)")
    # cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_embedding ON private_knowledge USING hnsw (embedding vector_cosine_ops)")

    # Tier 3 — PII-scrubbed shareable knowledge
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            seq_id              BIGSERIAL,
            source_intelligence_ids  TEXT[] NOT NULL DEFAULT '{}',
            knowledge_type         TEXT,
            name                TEXT NOT NULL,
            content             TEXT NOT NULL,
            summary             TEXT,
            embedding           vector,
            visibility          TEXT DEFAULT 'shared',
            tags                TEXT[] DEFAULT '{}',
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge (knowledge_type)")
    # cursor.execute("CREATE INDEX IF NOT EXISTS idx_lessons_embedding ON public_knowledge USING hnsw (embedding vector_cosine_ops)")

    # Audit log
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

    # Webhook sources
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

    # Outbound webhook rules
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_outbound_webhooks (
            id                          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name                        TEXT NOT NULL,
            url                         TEXT NOT NULL,
            debounce_ms                 INT DEFAULT 60000,
            conditions                  JSONB DEFAULT '{}',
            payload_mode                TEXT DEFAULT 'trigger_only',
            include_latest_memory       BOOLEAN DEFAULT TRUE,
            is_active                   BOOLEAN DEFAULT TRUE,
            created_at                  TIMESTAMPTZ DEFAULT NOW(),
            updated_at                  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_outbound_webhooks_active ON memory_outbound_webhooks (is_active)")


def _run_migrations(cursor):
    """Idempotent schema migrations for existing installations."""
    
    # ─── Taxonomy Migration ───
    try:
        # Check if old tables exist to avoid crashing
        cursor.execute("SELECT to_regclass('public.insights')")
        if cursor.fetchone()[0] is not None:
            cursor.execute("ALTER TABLE insights RENAME TO private_knowledge")
            cursor.execute("ALTER INDEX IF EXISTS idx_insights_entity RENAME TO idx_private_knowledge_entity")
            cursor.execute("ALTER INDEX IF EXISTS idx_insights_status RENAME TO idx_private_knowledge_status")
        
        cursor.execute("SELECT to_regclass('public.lessons')")
        if cursor.fetchone()[0] is not None:
            cursor.execute("ALTER TABLE lessons RENAME TO public_knowledge")
            cursor.execute("ALTER INDEX IF EXISTS idx_lessons_type RENAME TO idx_knowledge_type")
        
        cursor.execute("SELECT to_regclass('public.memory_lesson_types')")
        if cursor.fetchone()[0] is not None:
            cursor.execute("ALTER TABLE memory_lesson_types RENAME TO memory_knowledge_types")
            
        # Rename columns if they exist
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='intelligence' AND column_name='insight_type') THEN
                    ALTER TABLE intelligence RENAME COLUMN insight_type TO knowledge_type;
                END IF;
                IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='knowledge' AND column_name='lesson_type') THEN
                    ALTER TABLE knowledge RENAME COLUMN lesson_type TO knowledge_type;
                END IF;
                IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='knowledge' AND column_name='source_insight_ids') THEN
                    ALTER TABLE knowledge RENAME COLUMN source_insight_ids TO source_intelligence_ids;
                END IF;
            END
            $$;
        """)
        
        # Rename keys in JSONB settings — go directly to final names
        cursor.execute("""
            UPDATE memory_llm_configs SET task_type = 'intelligence_generation' WHERE task_type = 'insight_generation';
            UPDATE memory_llm_configs SET task_type = 'knowledge_generation' WHERE task_type = 'lesson_generation';
            UPDATE memory_llm_configs SET task_type = 'intelligence_generation' WHERE task_type = 'private_knowledge_generation';
            UPDATE memory_llm_configs SET task_type = 'knowledge_generation' WHERE task_type = 'public_knowledge_generation';
            UPDATE memory_system_prompts SET prompt_type = 'intelligence_generation' WHERE prompt_type = 'insight_generation';
            UPDATE memory_system_prompts SET prompt_type = 'knowledge_generation' WHERE prompt_type = 'lesson_generation';
            UPDATE memory_system_prompts SET prompt_type = 'intelligence_generation' WHERE prompt_type = 'private_knowledge_generation';
            UPDATE memory_system_prompts SET prompt_type = 'knowledge_generation' WHERE prompt_type = 'public_knowledge_generation';
        """)

        # Rename memory_settings.auto_public_knowledge_enabled -> auto_knowledge_enabled
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='memory_settings' AND column_name='auto_public_knowledge_enabled') THEN
                    IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='memory_settings' AND column_name='auto_knowledge_enabled') THEN
                        ALTER TABLE memory_settings DROP COLUMN auto_public_knowledge_enabled;
                    ELSE
                        ALTER TABLE memory_settings RENAME COLUMN auto_public_knowledge_enabled TO auto_knowledge_enabled;
                    END IF;
                END IF;
            END
            $$;
        """)
    except Exception as e:
        logger.warning(f"Taxonomy migration skipped/failed: {e}")
        
    # Add description column to all config-type lookup tables
    for tbl in ["memory_entity_types", "memory_entity_subtypes",
                "memory_knowledge_types", "memory_channel_types"]:
        cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS description TEXT")

    # Add seq_id to all core memory tier tables
    for tbl in ["interactions", "memories", "intelligence", "knowledge"]:
        try:
            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS seq_id BIGSERIAL")
        except Exception as e:
            logger.error(f"Failed to add seq_id to {tbl}: {e}")

    # Add embedding vector to interactions for Ephemeral Search
    try:
        cursor.execute("ALTER TABLE interactions ADD COLUMN IF NOT EXISTS embedding vector")
        cursor.execute("ALTER TABLE interactions ADD COLUMN IF NOT EXISTS processing_errors JSONB DEFAULT '{}'")
    except Exception as e:
        logger.error(f"Failed to add columns to interactions: {e}")

    # Agent columns that were added iteratively
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

    # LLM config columns migration
    try:
        cursor.execute("ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS provider_id TEXT REFERENCES memory_llm_providers(id) ON DELETE SET NULL")
        cursor.execute("ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS extra_config_json TEXT DEFAULT '{}'")
        cursor.execute("ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS prompt_id TEXT")
        cursor.execute("ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS inline_system_prompt TEXT")
        cursor.execute("ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS inline_schema TEXT")
        for col in ["provider", "name", "api_base_url", "api_key_encrypted", "api_key_preview"]:
            cursor.execute(f"ALTER TABLE memory_llm_configs DROP COLUMN IF EXISTS {col}")
    except Exception as e:
        logger.error(f"Failed to migrate llm configs: {e}")

    try:
        cursor.execute("""
            INSERT INTO memory_llm_configs (task_type, provider_id, model_name, is_active)
            SELECT 'memory_generation', (SELECT id FROM memory_llm_providers WHERE provider = 'openai' LIMIT 1), 'gpt-4o-mini', TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM memory_llm_configs WHERE task_type = 'memory_generation' AND is_active = TRUE
            )
        """)
    except Exception as e:
        logger.error(f"Failed to seed memory_generation llm config: {e}")

    # 🗂️ Pipeline & Drag-and-Drop Migrations
    try:
        cursor.execute("ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS pipeline_stage TEXT")
        cursor.execute("ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS execution_order INT DEFAULT 0")

        # Backfill existing nodes into the 5 logical pipelines based on their legacy task_type
        # ONLY for rows that have never been assigned a pipeline_stage (first-time migration).
        # This prevents overwriting user-configured drag-and-drop ordering on server restarts.
        
        # Interactions Pipeline
        cursor.execute("UPDATE memory_llm_configs SET pipeline_stage = 'interactions', execution_order = 0 WHERE task_type = 'vision' AND pipeline_stage IS NULL")
        
        # Memories Pipeline
        cursor.execute("UPDATE memory_llm_configs SET pipeline_stage = 'memories', execution_order = 0 WHERE task_type = 'entity_extraction' AND pipeline_stage IS NULL")
        cursor.execute("UPDATE memory_llm_configs SET pipeline_stage = 'memories', execution_order = 1 WHERE task_type = 'embedding' AND pipeline_stage IS NULL")
        cursor.execute("UPDATE memory_llm_configs SET pipeline_stage = 'memories', execution_order = 2 WHERE task_type = 'memory_generation' AND pipeline_stage IS NULL")
        
        # Intelligence Pipeline
        cursor.execute("UPDATE memory_llm_configs SET pipeline_stage = 'intelligence', execution_order = 0 WHERE task_type = 'intelligence_generation' AND pipeline_stage IS NULL")
        
        # Knowledge Pipeline
        cursor.execute("UPDATE memory_llm_configs SET pipeline_stage = 'knowledge', execution_order = 0 WHERE task_type = 'pii_scrubbing' AND pipeline_stage IS NULL")
        cursor.execute("UPDATE memory_llm_configs SET pipeline_stage = 'knowledge', execution_order = 1 WHERE task_type = 'knowledge_generation' AND pipeline_stage IS NULL")

    except Exception as e:
        logger.warning(f"Pipeline schema migration skipped/failed: {e}")

    # Settings columns
    for col, col_def in [
        ("supabase_db_url", "TEXT"),
        ("memory_generation_time", "TEXT DEFAULT '02:00'"),
        ("memory_generation_mode", "TEXT DEFAULT 'ner_and_raw'"),
        ("knowledge_threshold", "INT DEFAULT 5"),
        ("intelligence_extraction_threshold", "INT DEFAULT 10"),
        ("prior_context_chrono_count", "INT DEFAULT 2"),
        ("prior_context_semantic_count", "INT DEFAULT 2"),
        ("prior_intelligence_chrono_count", "INT DEFAULT 3"),
        ("prior_intelligence_semantic_count", "INT DEFAULT 2"),
        ("prior_knowledge_semantic_count", "INT DEFAULT 3"),
        ("prior_knowledge_in_intelligence_count", "INT DEFAULT 2"),
    ]:
        cursor.execute(f"ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS {col} {col_def}")

    # Entity type config columns
    for col, col_def in [
        ("ner_schema", "JSONB DEFAULT NULL"),
        ("knowledge_extraction_threshold", "INT DEFAULT NULL"),
        ("embedding_enabled", "BOOLEAN DEFAULT TRUE"),
        ("pii_scrub_knowledge", "BOOLEAN DEFAULT TRUE"),
        ("metadata_field_map", "JSONB DEFAULT '{}'"),
        ("intelligence_signals_prompt", "JSONB DEFAULT NULL"),
        ("knowledge_signals_prompt", "JSONB DEFAULT NULL"),
    ]:
        cursor.execute(f"ALTER TABLE memory_entity_type_config ADD COLUMN IF NOT EXISTS {col} {col_def}")
                
    # Migrate signal columns from TEXT to JSONB (if they were created as TEXT in a prior version)
    for col in ("intelligence_signals_prompt", "knowledge_signals_prompt"):
        try:
            cursor.execute(f"""
                ALTER TABLE memory_entity_type_config
                ALTER COLUMN {col} TYPE JSONB USING {col}::jsonb
            """)
        except Exception:
            conn.rollback()  # Column already JSONB or empty — safe to skip

    # Drop legacy and dead columns
    try:
        cursor.execute("ALTER TABLE memory_settings DROP COLUMN IF EXISTS knowledge_trigger_days")
        cursor.execute("ALTER TABLE memory_entity_type_config DROP COLUMN IF EXISTS insight_trigger_days")
        cursor.execute("ALTER TABLE memory_entity_type_config DROP COLUMN IF EXISTS intelligence_trigger_days")
        cursor.execute("ALTER TABLE memory_settings DROP COLUMN IF EXISTS pii_scrubbing_enabled")
        cursor.execute("ALTER TABLE memory_settings DROP COLUMN IF EXISTS auto_share_scrubbed")
    except Exception as e:
        logger.warning(f"Drop legacy columns skipped: {e}")
        
    # Rename compaction_threshold to intelligence_extraction_threshold safely
    try:
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='memory_entity_type_config' AND column_name='compaction_threshold') THEN
                    ALTER TABLE memory_entity_type_config RENAME COLUMN compaction_threshold TO intelligence_extraction_threshold;
                END IF;
            END
            $$;
        """)
    except Exception as e:
        logger.warning(f"Rename compaction_threshold skipped: {e}")

    # Job log table (safe to CREATE IF NOT EXISTS in migration too)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_job_log (
            job_name    TEXT PRIMARY KEY,
            last_run    TIMESTAMPTZ,
            last_date   DATE
        )
    """)

    # Memories columns added after initial deploy
    for col, col_def in [
        ("updated_at", "TIMESTAMPTZ DEFAULT NOW()"),
        ("compacted_at", "TIMESTAMPTZ"),
        ("processing_errors", "JSONB DEFAULT '{}'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE memories ADD COLUMN IF NOT EXISTS {col} {col_def}")
        except Exception as e:
            logger.error(f"Failed to add {col} to memories: {e}")

    # LLM Providers columns added after initial deploy
    for col, col_def in [
        ("rate_limit_rpm", "INT DEFAULT 60"),
        ("max_retries", "INT DEFAULT 3"),
        ("retry_delay_ms", "INT DEFAULT 1000"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE memory_llm_providers ADD COLUMN IF NOT EXISTS {col} {col_def}")
        except Exception as e:
            logger.error(f"Failed to add {col} to memory_llm_providers: {e}")

    # Interactions columns added for reactive webhooks
    for col, col_def in [
        ("is_enriched", "BOOLEAN DEFAULT FALSE"),
        ("outbound_webhooks_fired", "TEXT[] DEFAULT '{}'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE interactions ADD COLUMN IF NOT EXISTS {col} {col_def}")
        except Exception as e:
            logger.error(f"Failed to add {col} to interactions: {e}")


def init_memory_db():
    """Initialize all memory system tables in PostgreSQL. Idempotent."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        _enable_extensions(cursor)
        
        # Seamless Migration: private_knowledge -> intelligence, public_knowledge -> knowledge
        try:
            cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_name='private_knowledge'")
            if cursor.fetchone():
                cursor.execute("ALTER TABLE private_knowledge RENAME TO intelligence")
                cursor.execute("ALTER INDEX IF EXISTS idx_insights_entity RENAME TO idx_intelligence_entity")
                cursor.execute("ALTER INDEX IF EXISTS idx_private_knowledge_entity RENAME TO idx_intelligence_entity")
                cursor.execute("ALTER INDEX IF EXISTS idx_insights_status RENAME TO idx_intelligence_status")
                cursor.execute("ALTER INDEX IF EXISTS idx_private_knowledge_status RENAME TO idx_intelligence_status")
        except Exception as e:
            logger.warning(f"Failed to rename private_knowledge to intelligence: {e}")
            
        try:
            cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_name='public_knowledge'")
            if cursor.fetchone():
                cursor.execute("ALTER TABLE public_knowledge RENAME TO knowledge")
                cursor.execute("ALTER INDEX IF EXISTS idx_lessons_type RENAME TO idx_knowledge_type")
                cursor.execute("ALTER INDEX IF EXISTS idx_public_knowledge_type RENAME TO idx_knowledge_type")
                
                # Check column and rename
                cursor.execute("SELECT 1 FROM information_schema.columns WHERE table_name='knowledge' AND column_name='source_private_knowledge_ids'")
                if cursor.fetchone():
                    cursor.execute("ALTER TABLE knowledge RENAME COLUMN source_private_knowledge_ids TO source_intelligence_ids")
        except Exception as e:
            logger.warning(f"Failed to rename public_knowledge to knowledge: {e}")

        _create_config_tables(cursor)
        _create_interaction_tables(cursor)
        _create_memory_tier_tables(cursor)
        _run_migrations(cursor)
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

        # Knowledge types
        for name, color in [
            ("process", "#22C55E"), ("risk", "#EF4444"), ("sales", "#3B82F6"),
            ("product", "#8B5CF6"), ("support", "#F59E0B"), ("other", "#6B7280")
        ]:
            cursor.execute(
                "INSERT INTO memory_knowledge_types (name, color) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
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
                 "You are an AI memory system. Based on the provided interaction data, write a concise factual memory record.\n\nPRIOR CONTEXT RULES:\n- Previous memories for this entity are provided under 'Prior Context'.\n- These represent ESTABLISHED facts. Do NOT repeat them.\n- Focus EXCLUSIVELY on NEW information from today's interactions.\n- Note any progressions, status changes, or contradictions with prior records.\n- If today's interactions contain no new information beyond prior context, write a brief note stating the interaction occurred with no significant new details.\n\nOUTPUT RULES:\n- Return only the summary text, 2-5 sentences.\n- Focus on key facts, decisions, named entities, and action items.",
                 ""),
                ("intelligence_generation", "openai", "gpt-4o-mini", "intelligence", 0,
                 "You are an AI analyst reviewing interaction history for a specific entity. Based on the provided memory summaries, identify a meaningful pattern, risk, opportunity, or behavioral insight. Return JSON: {\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\"}. knowledge_type must be one of: behavior_pattern, risk_signal, opportunity, relationship_shift, preference, milestone.",
                 ""),
                ("pii_scrubbing", "zendata", "", "knowledge", 0, "", ""),
                ("knowledge_generation", "openai", "gpt-4o-mini", "knowledge", 1,
                 "You are an AI knowledge curator. The following are de-identified intelligence from multiple interactions. Synthesize them into a single generalizable Knowledge item — a durable, reusable piece of knowledge applicable beyond any specific entity. Remove all specific names. Return JSON: {\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\", \"tags\": [...]}\nknowledge_type must be one of: process, risk, sales, product, support, other",
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
             "Based on the provided memory summaries, identify a meaningful pattern, risk, opportunity, "
             "or behavioral insight. Return JSON: {\"name\": \"...\", \"knowledge_type\": \"...\", "
             "\"content\": \"...\", \"summary\": \"...\"}. "
             "knowledge_type must be one of: behavior_pattern, risk_signal, opportunity, relationship_shift, preference, milestone."),
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
        """, ('{\n  "name": "...",\n  "knowledge_type": "...",\n  "content": "...",\n  "summary": "..."\n}',))

        # Default entity type configs
        for entity_type in ["contact", "institution", "program", "supplier", "product"]:
            cursor.execute("""
                INSERT INTO memory_entity_type_config (entity_type)
                VALUES (%s)
                ON CONFLICT (entity_type) DO NOTHING
            """, (entity_type,))

        logger.info("Memory system defaults seeded")


