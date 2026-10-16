-- TASK-257 §3 migration 002 — cutover: reconcile legacy deployments onto the
-- frozen baseline and drop what the freeze retired.
--
-- GATE SATISFIED 2026-10-16 (owner go-ahead "make the backup and proceed"):
--   * phase-1 stamp verified on prod (schema_migrations = 001_baseline,
--     deploy action cmvam60nz013c06nw4ld60kcn done 06:59:27Z);
--   * pre-cutover backup taken and pg_restore-validated
--     (/var/lib/postgresql/data/backups/pre_task257_s3_002_20261016.dump,
--     custom format, 312 TOC entries, inside the persistent postgres volume);
--   * rehearsed against a schema-only copy of prod before this deploy.
--
-- Drafted 2026-10-16 from the §3 drift inventory (prod uwzosvzy, counts-only):
--   orphan fossils (zero code readers/creators once the phase-2 deletion of
--     _run_migrations lands): insights=0, lessons=0, memory_lesson_types=6
--   batch transport rows: runs=4, requests=1000, sources=25000 (§2 precedent:
--     owner chose DELETE)
--   KEPT: users (live auth table from core/db_init),
--         _quarantine_orphaned_llm_keys_20261015 (keys re-entry pending)
--   KEPT (deferred, NOT orphans): the prompt-console fossil tables
--     (settings, prompts, prompt_versions, prompt_variables, pm_files,
--     account_variables, api_keys, templates) are still CREATED at boot by
--     db_init.init_db() and still read/written by live routes
--     (routes/prompts.py, templates.py, variables.py, api_keys.py,
--     services/prompt_renderer.py, config_helpers.py, storage_service.py).
--     Dropping them here would resurrect on the next boot and 500 live
--     endpoints. Their retirement (db_init shrink + route removal) is the
--     §3 follow-up, not this migration.
--
-- Idempotent: a fresh 001 database no-ops through every statement.

-- 1. Retire the deleted provider-batch transport (children first).

DROP TABLE IF EXISTS memory_provider_batch_request_sources;
DROP TABLE IF EXISTS memory_provider_batch_requests;
DROP TABLE IF EXISTS memory_provider_batch_runs;

-- 2. Drop the legacy-taxonomy orphan fossils. insights/lessons MUST go
--    before step 4: the boot rename-compat blocks renamed their indexes to
--    the baseline names while leaving them physically on the fossils
--    (verified 2026-10-16: idx_intelligence_entity/idx_intelligence_status
--    are ON insights; idx_knowledge_type is ON lessons). Dropping the
--    fossils frees the squatted names; baseline has no idx_knowledge_type,
--    so it just goes away with lessons.
--    Root cause of the fossils: the taxonomy renames in _run_migrations
--    never ran on prod — the try block's first statement failed and the
--    warning was swallowed (TASK-257 §3).
--    Scope note: only these three are safe to drop. Every other fossil
--    table has a live boot-time creator (db_init) and/or live route
--    readers — see the header.

DROP TABLE IF EXISTS insights;
DROP TABLE IF EXISTS lessons;
DROP TABLE IF EXISTS memory_lesson_types;

-- 3. Reconcile memory_settings.
--    Add the only auto-knowledge knob names code reads (models.py; prod
--    lacks them so the knob silently defaults and a settings PUT targeting
--    them would 500). Drop the legacy equivalents (prod values were 5 =
--    defaults — nothing to migrate) and the credential-envelope columns
--    (supabase_db_url verified NULL on prod 2026-10-16; paired code removal
--    ships in the same deploy — secrets sweep, rewrap endpoint, remediation
--    script).

ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS auto_knowledge_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS auto_knowledge_threshold INT DEFAULT 5;
ALTER TABLE memory_settings DROP COLUMN IF EXISTS lesson_threshold;
ALTER TABLE memory_settings DROP COLUMN IF EXISTS lesson_trigger_days;
ALTER TABLE memory_settings DROP COLUMN IF EXISTS public_knowledge_threshold;
ALTER TABLE memory_settings DROP COLUMN IF EXISTS public_knowledge_trigger_days;
ALTER TABLE memory_settings DROP COLUMN IF EXISTS supabase_url;
ALTER TABLE memory_settings DROP COLUMN IF EXISTS supabase_db_url;
ALTER TABLE memory_settings DROP COLUMN IF EXISTS supabase_connected;

-- 4. Restore frozen identity on the live tier-2/3 tables.
--    The baseline-named indexes land here (frees in step 2). Plain CREATE
--    INDEX, not CONCURRENTLY: this runs once at boot before the app serves;
--    on prod the intelligence table is small and the deploy restarts anyway.
--    Then rename the rename-compat sequence/pkey names to the frozen ones —
--    ALTER keeps the OID, so the seq_id defaults keep working and pg_dump
--    renders the new names from here on.

CREATE INDEX IF NOT EXISTS idx_intelligence_entity ON intelligence (primary_entity_type, primary_entity_id);
CREATE INDEX IF NOT EXISTS idx_intelligence_status ON intelligence (status);
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);

ALTER SEQUENCE IF EXISTS private_knowledge_seq_id_seq RENAME TO intelligence_seq_id_seq;
ALTER SEQUENCE IF EXISTS public_knowledge_seq_id_seq RENAME TO knowledge_seq_id_seq;
ALTER INDEX IF EXISTS private_knowledge_pkey RENAME TO intelligence_pkey;
ALTER INDEX IF EXISTS public_knowledge_pkey RENAME TO knowledge_pkey;

-- 5. Drop retired entity-type-config columns (zero code readers; fresh
--    installs never had them).

ALTER TABLE memory_entity_type_config DROP COLUMN IF EXISTS pii_scrub_lessons;
ALTER TABLE memory_entity_type_config DROP COLUMN IF EXISTS private_knowledge_trigger_days;
