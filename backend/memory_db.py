"""
memory_db.py — PostgreSQL schema + initialization for the Memory System

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
    # memory_knowledge_types retired — knowledge is classified by `category`
    # (structural) + `signals` (domain), not a user-defined type list.
    # Table is dropped further below after legacy migrations run.
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
            prompt_version      TEXT DEFAULT 'v1',
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
            has_attachments         BOOLEAN DEFAULT FALSE,
            attachment_refs         JSONB DEFAULT '[]',
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

    # Entity profiles — stores per-entity instance data extracted from CRM blobs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_profiles (
            entity_type       TEXT NOT NULL,
            entity_id         TEXT NOT NULL,
            display_name      TEXT,
            subtype           TEXT,
            status            TEXT,
            properties        JSONB DEFAULT '{}',
            first_seen_at     TIMESTAMPTZ DEFAULT NOW(),
            last_synced_at    TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (entity_type, entity_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_profiles_type ON entity_profiles (entity_type)")


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
            signals             TEXT[] NOT NULL DEFAULT '{}',
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
            signals             TEXT[] NOT NULL DEFAULT '{}',
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
    # category/status/signals indexes created after ALTER TABLE ADD COLUMN below

    # Playbook extraction: tracks which AI thought/tool-call interactions have been processed
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playbook_processed_interactions (
            interaction_id TEXT PRIMARY KEY,
            processed_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

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

    # Vision/Doc parsing completion webhooks. Fired once per successfully-parsed
    # attachment with the extracted text. Best-effort fire-once delivery.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vision_completion_webhooks (
            id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name            TEXT NOT NULL,
            url             TEXT NOT NULL,
            is_active       BOOLEAN DEFAULT TRUE,
            doc_type_filter JSONB DEFAULT NULL,
            source_filter   JSONB DEFAULT NULL,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vision_webhooks_active ON vision_completion_webhooks (is_active)")

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
            payload_interaction_types   JSONB DEFAULT NULL,
            payload_interaction_types_mode TEXT DEFAULT 'include',
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
                "memory_channel_types"]:
        cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS description TEXT")

    # Retire the orphaned memory_knowledge_types config table (ran after the
    # legacy memory_lesson_types→memory_knowledge_types rename above, so this
    # drops whatever that produced too).
    try:
        cursor.execute("DROP TABLE IF EXISTS memory_knowledge_types")
    except Exception as e:
        logger.error(f"Failed to drop memory_knowledge_types: {e}")

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

    # Intelligence: migrate legacy scalar `knowledge_type` → `signals` TEXT[] array.
    # Intelligence records are tagged with the signals defined per entity type
    # (memory_entity_type_config.intelligence_signals_prompt), not a generic taxonomy.
    try:
        cursor.execute("ALTER TABLE intelligence ADD COLUMN IF NOT EXISTS signals TEXT[] NOT NULL DEFAULT '{}'")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_intelligence_signals ON intelligence USING GIN (signals)")
        # Only backfill/drop if the legacy column still exists (skips fresh installs)
        cursor.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'intelligence' AND column_name = 'knowledge_type'
        """)
        if cursor.fetchone():
            # Backfill from the old comma-separated knowledge_type, trimming blanks/"other"
            cursor.execute("""
                UPDATE intelligence
                SET signals = ARRAY(
                    SELECT trim(s) FROM unnest(string_to_array(knowledge_type, ',')) AS s
                    WHERE trim(s) <> '' AND lower(trim(s)) <> 'other'
                )
                WHERE knowledge_type IS NOT NULL AND signals = '{}'
            """)
            cursor.execute("ALTER TABLE intelligence DROP COLUMN knowledge_type")
    except Exception as e:
        logger.error(f"Failed to migrate intelligence knowledge_type → signals: {e}")

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
        cursor.execute("ALTER TABLE memory_llm_configs ADD COLUMN IF NOT EXISTS prompt_version TEXT DEFAULT 'v1'")
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
        # Max output tokens for the memory-, intelligence- and knowledge-generation LLM calls
        ("memory_generation_max_tokens", "INT DEFAULT 1200"),
        ("intelligence_max_tokens", "INT DEFAULT 1200"),
        ("knowledge_max_tokens", "INT DEFAULT 1200"),
        # get-context knowledge injection: cap (30 preserves prior behavior) and
        # optional relevance floor (0 = keep the reorder-only, drop-nothing default)
        ("context_knowledge_count", "INT DEFAULT 30"),
        ("context_knowledge_min_similarity", "FLOAT DEFAULT 0.0"),
        # When a new precursor dedup-matches an existing knowledge/skill/playbook,
        # LLM-merge the new evidence into it (update-in-place) instead of only
        # bumping merge_count. Falls back to increment on any failure.
        ("knowledge_refine_on_merge", "BOOLEAN DEFAULT TRUE"),
        # Sprint 2.5 — governed knowledge facets + lean context injection
        ("context_knowledge_mode", "TEXT DEFAULT 'full'"),       # full | index
        ("facet_extraction_enabled", "BOOLEAN DEFAULT TRUE"),
        ("knowledge_facets_schema", "JSONB DEFAULT NULL"),        # global governed facet schema
        ("profile_facet_map", "JSONB DEFAULT NULL"),              # facet_key -> entity_profiles property key
        # ── Nightly learning cadence: per-tier schedule valve (dual-gate) ──
        # Intelligence (1→2): schedule sweep in addition to the threshold valve
        ("intelligence_schedule_enabled", "BOOLEAN DEFAULT TRUE"),
        ("intelligence_generation_time", "TEXT DEFAULT '02:30'"),
        ("intelligence_schedule_floor", "INT DEFAULT 2"),         # min uncompacted memories for nightly sweep
        # Knowledge (2→3): schedule sweep + the threshold valve
        ("knowledge_schedule_enabled", "BOOLEAN DEFAULT TRUE"),
        ("knowledge_generation_time", "TEXT DEFAULT '03:00'"),
        ("knowledge_schedule_floor", "INT DEFAULT 2"),            # min unused confirmed intelligence for nightly sweep
        # Playbooks: nightly cadence (was weekly-only)
        ("playbook_schedule_enabled", "BOOLEAN DEFAULT TRUE"),
        ("playbook_generation_time", "TEXT DEFAULT '03:30'"),
        # Telemetry reflection (AI telemetry → skill/playbook/knowledge, option B)
        ("telemetry_reflection_enabled", "BOOLEAN DEFAULT TRUE"),
        ("telemetry_reflection_time", "TEXT DEFAULT '04:00'"),
        ("telemetry_reflection_confidence_min", "FLOAT DEFAULT 0.6"),
        ("telemetry_reflection_max_tokens", "INT DEFAULT 1200"),
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
        ("discovered_schema", "JSONB DEFAULT NULL"),
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

    # Rename legacy auto-approve / auto-promote columns to current naming
    try:
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='memory_entity_type_config' AND column_name='insight_auto_approve')
                   AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='memory_entity_type_config' AND column_name='intelligence_auto_approve') THEN
                    ALTER TABLE memory_entity_type_config RENAME COLUMN insight_auto_approve TO intelligence_auto_approve;
                END IF;
                IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='memory_entity_type_config' AND column_name='lesson_auto_promote')
                   AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='memory_entity_type_config' AND column_name='knowledge_auto_promote') THEN
                    ALTER TABLE memory_entity_type_config RENAME COLUMN lesson_auto_promote TO knowledge_auto_promote;
                END IF;
            END
            $$;
        """)
    except Exception as e:
        logger.warning(f"Rename auto-approve columns skipped: {e}")

    # Ensure columns exist (for fresh DBs that never had legacy names but were created before this column was in CREATE TABLE)
    cursor.execute("ALTER TABLE memory_entity_type_config ADD COLUMN IF NOT EXISTS intelligence_auto_approve BOOLEAN DEFAULT FALSE")
    cursor.execute("ALTER TABLE memory_entity_type_config ADD COLUMN IF NOT EXISTS knowledge_auto_promote BOOLEAN DEFAULT FALSE")

    # Job log table (safe to CREATE IF NOT EXISTS in migration too)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_job_log (
            job_name    TEXT PRIMARY KEY,
            last_run    TIMESTAMPTZ,
            last_date   DATE
        )
    """)

    # Pipeline run observability (one row per check/generation run)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_pipeline_runs (
            id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            seq_id          BIGSERIAL,
            job             TEXT NOT NULL,
            outcome         TEXT NOT NULL,
            reason_code     TEXT,
            records_created INT DEFAULT 0,
            detail          JSONB DEFAULT '{}',
            trigger         TEXT DEFAULT 'scheduled',
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_job ON memory_pipeline_runs (job, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created ON memory_pipeline_runs (created_at DESC)")

    # Telemetry reflection idempotency log — one row per (entity, day) reflected on
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_reflection_log (
            entity_type         TEXT NOT NULL,
            entity_id           TEXT NOT NULL,
            reflection_date     DATE NOT NULL,
            candidates_created  INT DEFAULT 0,
            reflected_at        TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (entity_type, entity_id, reflection_date)
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

    # Interactions columns added for attachments + reactive webhooks
    for col, col_def in [
        ("has_attachments", "BOOLEAN DEFAULT FALSE"),
        ("attachment_refs", "JSONB DEFAULT '[]'"),
        ("is_enriched", "BOOLEAN DEFAULT FALSE"),
        ("outbound_webhooks_fired", "TEXT[] DEFAULT '{}'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE interactions ADD COLUMN IF NOT EXISTS {col} {col_def}")
        except Exception as e:
            logger.error(f"Failed to add {col} to interactions: {e}")

    # Outbound webhook: payload-level interaction-type filter.
    # NULL or empty array = include all types (backward compatible).
    try:
        cursor.execute(
            "ALTER TABLE memory_outbound_webhooks ADD COLUMN IF NOT EXISTS payload_interaction_types JSONB DEFAULT NULL"
        )
    except Exception as e:
        logger.error(f"Failed to add payload_interaction_types to memory_outbound_webhooks: {e}")

    # Outbound webhook: include/exclude mode for the interaction-type filter.
    try:
        cursor.execute(
            "ALTER TABLE memory_outbound_webhooks ADD COLUMN IF NOT EXISTS payload_interaction_types_mode TEXT DEFAULT 'include'"
        )
    except Exception as e:
        logger.error(f"Failed to add payload_interaction_types_mode to memory_outbound_webhooks: {e}")

    # Memory threshold trigger: generate a memory every N qualifying interactions
    # in addition to the daily schedule (whichever comes first). The safe
    # boundary types list gates *when* the threshold-triggered job may fire so
    # we never split mid-conversation.
    for col, col_def in [
        ("memory_threshold", "INT DEFAULT 0"),  # 0 = threshold disabled; daily-only
        ("memory_safe_boundary_types", "JSONB DEFAULT '[\"outgoing_whatsapp_message\"]'::jsonb"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS {col} {col_def}")
        except Exception as e:
            logger.error(f"Failed to add {col} to memory_settings: {e}")

    # ── Knowledge unified table: category + metadata + quality gauges ──────
    knowledge_cols = [
        ("category", "TEXT DEFAULT 'trade_knowledge'"),
        ("signals", "TEXT[] NOT NULL DEFAULT '{}'"),
        ("metadata", "JSONB DEFAULT '{}'"),
        ("merge_count", "INT DEFAULT 0"),
        ("last_merged_at", "TIMESTAMPTZ"),
        ("quality_score", "FLOAT"),
        ("evidence_breadth", "INT DEFAULT 1"),
        ("outcome_signal", "FLOAT DEFAULT 0.0"),
        ("extraction_confidence", "FLOAT DEFAULT 0.5"),
        ("source_pathway", "TEXT DEFAULT 'experiential'"),
        ("source_ai_interaction_ids", "TEXT[] DEFAULT '{}'"),
        ("success_count", "INT DEFAULT 0"),
        ("failure_count", "INT DEFAULT 0"),
        ("feedback_notes", "JSONB DEFAULT '[]'"),
        ("version", "INT DEFAULT 1"),
        ("parent_id", "TEXT"),
        ("status", "TEXT DEFAULT 'confirmed'"),
    ]
    for col, col_def in knowledge_cols:
        try:
            cursor.execute(f"ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS {col} {col_def}")
        except Exception as e:
            logger.error(f"Failed to add {col} to knowledge: {e}")

    # Indexes for new columns (must run after ALTER TABLE)
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge (category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_status ON knowledge (status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_signals ON knowledge USING GIN (signals)")
        # GIN for JSONB containment filtering on metadata.facets (hard facet filter)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_metadata_gin ON knowledge USING GIN (metadata jsonb_path_ops)")
    except Exception as e:
        logger.error(f"Failed to create knowledge indexes: {e}")

    # Backfill existing knowledge: set category + status where NULL
    try:
        cursor.execute("UPDATE knowledge SET category = 'trade_knowledge' WHERE category IS NULL")
        cursor.execute("UPDATE knowledge SET status = 'active' WHERE status = 'confirmed' AND category IS NOT NULL")
    except Exception as e:
        logger.error(f"Failed to backfill knowledge category/status: {e}")

    # Knowledge: migrate legacy scalar `knowledge_type` → `signals` TEXT[] array.
    # Knowledge records carry the domain signals defined per entity type
    # (memory_entity_type_config.knowledge_signals_prompt). `category` (the
    # structural kind: best_practices/lessons_learned/trade_knowledge/skill/playbook)
    # is a separate axis and is kept. The old knowledge_type was either a duplicate
    # of category (skill/playbook/hermes) or a free-text "other" — both discarded.
    try:
        cursor.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'knowledge' AND column_name = 'knowledge_type'
        """)
        if cursor.fetchone():
            cursor.execute("""
                UPDATE knowledge
                SET signals = ARRAY(
                    SELECT trim(s) FROM unnest(string_to_array(knowledge_type, ',')) AS s
                    WHERE trim(s) <> ''
                      AND lower(trim(s)) NOT IN ('other', 'skill', 'playbook',
                          'best_practices', 'lessons_learned', 'trade_knowledge')
                      AND trim(s) <> coalesce(category, '')
                )
                WHERE knowledge_type IS NOT NULL AND signals = '{}'
            """)
            cursor.execute("ALTER TABLE knowledge DROP COLUMN knowledge_type")
    except Exception as e:
        logger.error(f"Failed to migrate knowledge knowledge_type → signals: {e}")

    # ── Global gauges (memory_settings) ────────────────────────────────────
    settings_gauge_cols = [
        ("dedup_similarity_threshold", "FLOAT DEFAULT 0.85"),
        ("extraction_confidence_threshold", "FLOAT DEFAULT 0.6"),
        ("consolidation_similarity_threshold", "FLOAT DEFAULT 0.80"),
        ("consolidation_run_interval_days", "INT DEFAULT 7"),
        ("memory_generation_interaction_types", "JSONB DEFAULT '[\"internal_ai_thought\", \"internal_ai_tool_call\"]'::jsonb"),
        ("playbook_extraction_interval_days", "INT DEFAULT 7"),
        ("playbook_extraction_evidence_threshold", "INT DEFAULT 20"),
    ]
    for col, col_def in settings_gauge_cols:
        try:
            cursor.execute(f"ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS {col} {col_def}")
        except Exception as e:
            logger.error(f"Failed to add {col} to memory_settings: {e}")

    # ── Per-entity-type gauges (memory_entity_type_config) ─────────────────
    entity_gauge_cols = [
        ("extraction_min_entities", "INT DEFAULT 3"),
        ("outcome_positive_threshold", "FLOAT DEFAULT 0.7"),
        ("auto_activate_score_threshold", "FLOAT"),
        ("decay_max_inactive_days", "INT DEFAULT 90"),
        ("decay_min_interactions_since_trigger", "INT DEFAULT 100"),
        ("playbook_auto_activate", "BOOLEAN DEFAULT FALSE"),
        ("skill_auto_activate", "BOOLEAN DEFAULT FALSE"),
    ]
    for col, col_def in entity_gauge_cols:
        try:
            cursor.execute(f"ALTER TABLE memory_entity_type_config ADD COLUMN IF NOT EXISTS {col} {col_def}")
        except Exception as e:
            logger.error(f"Failed to add {col} to memory_entity_type_config: {e}")


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
                 "You are an AI knowledge curator. The following are de-identified intelligence from multiple interactions. Synthesize them into a single generalizable Knowledge item — a durable, reusable piece of knowledge applicable beyond any specific entity. Remove all specific names.\n\nFocus on these knowledge signals:\n\n{{ knowledge_signals }}\n\nReturn JSON: {\"name\": \"...\", \"category\": \"...\", \"content\": \"...\", \"summary\": \"...\", \"tags\": [...]}\ncategory must be one of:\n- best_practices: Behavioral rules (Dos and Don'ts) proven to work through experience\n- lessons_learned: Specific negative outcomes with root-cause analysis — what went wrong and why\n- trade_knowledge: Domain-specific procedural, regulatory, or technical facts (default)\n\ntags: Freeform domain labels (e.g., \"sales\", \"risk\", \"visa\", \"objection-handling\"). Use 1-3 tags.",
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
            from memory_playbooks import _PLAYBOOK_GEN_PROMPT, _SKILL_GEN_PROMPT
            from memory_telemetry import _REFLECTION_SYSTEM_PROMPT
            pick_nodes = [
                ("playbook_generation", 2, _PLAYBOOK_GEN_PROMPT),
                ("skill_generation", 3, _SKILL_GEN_PROMPT),
                ("telemetry_reflection", 4, _REFLECTION_SYSTEM_PROMPT),
            ]
        except Exception as e:
            logger.warning(f"Could not import generation prompt constants for seeding: {e}")
            pick_nodes = [
                ("playbook_generation", 2, ""), ("skill_generation", 3, ""), ("telemetry_reflection", 4, ""),
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

        # Sprint 2.5 — seed global facets schema + always-on Knowledge Management skill
        try:
            from memory_facets import seed_default_facets_schema, seed_management_skill
            seed_default_facets_schema()
            seed_management_skill()
        except Exception as e:
            logger.warning(f"Sprint 2.5 seeding skipped: {e}")

        logger.info("Memory system defaults seeded")


