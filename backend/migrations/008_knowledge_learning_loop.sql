-- 008: knowledge learning loop (docs/plans/knowledge-learning-loop.md §2, §5).
--
-- Closes the learn-half of the knowledge tier:
--   knowledge_usage_events — one row per knowledge record actually served
--     into agent context (get-context / semantic search / fulltext search),
--     resolved nightly by the knowledge_outcome_attribution job against
--     downstream signals (lessons_learned echo, confirmed recurrence).
--     The event row IS the outcome ledger — no separate outcomes table.
--   knowledge.usage_count — denormalized served-count for admin stats and
--     retirement scans (no aggregate per request).
--   memory_settings columns — the nine learning-loop dials (§5). Defaults
--     here match the Pydantic defaults in store/models.py.

CREATE TABLE IF NOT EXISTS knowledge_usage_events (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_id   TEXT NOT NULL,          -- knowledge.id is TEXT (lenient by design: no FK, no format promise)
    interaction_id UUID,                   -- interaction this context served (NULL for bare search)
    agent_id       TEXT,
    pathway        TEXT NOT NULL,          -- 'get_context' | 'semantic_search' | 'fulltext_search'
    entity_type    TEXT,
    entity_id      TEXT,
    rank           INT,                    -- 1-based position in the injected/returned list
    attributed_at  TIMESTAMPTZ,            -- idempotency cursor for the attribution job
    outcome        TEXT,                   -- NULL until attributed: 'success' | 'failure' | 'no_signal'
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kue_knowledge ON knowledge_usage_events (knowledge_id, created_at);
CREATE INDEX IF NOT EXISTS idx_kue_unattributed ON knowledge_usage_events (created_at) WHERE attributed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_kue_interaction ON knowledge_usage_events (interaction_id);

-- Denormalized for admin stats / retirement scans without an aggregate per request.
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS usage_count INT NOT NULL DEFAULT 0;

ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_learning_usage_capture BOOLEAN DEFAULT TRUE;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_learning_max_events_per_call INT DEFAULT 50;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_learning_attribution_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_learning_negative_window_days INT DEFAULT 7;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_learning_negative_similarity DOUBLE PRECISION DEFAULT 0.80;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_learning_min_signal_age_hours INT DEFAULT 6;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_learning_retire_after_days INT DEFAULT 90;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_learning_refine_min_failures INT DEFAULT 2;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS knowledge_retrieval_quality_weight DOUBLE PRECISION DEFAULT 0.0;
