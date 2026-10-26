-- 007: retire the playbook category in favor of skills.
--
-- Playbooks and skills were both `category` values on the unified knowledge
-- table, both rendered as SKILL.md (the agent-skills standard has no separate
-- playbook format). Playbooks are gone: existing playbook rows become skills,
-- the extraction pipeline generates skills directly from intelligence
-- clusters (no intermediate playbook → decomposition hop), and playbook-only
-- settings/LLM nodes are removed.
--
-- Data notes:
--   - knowledge rows: metadata already carries steps/trigger_conditions and
--     `content` already stores the full SKILL.md document, so the category
--     flip is lossless.
--   - memory_job_log rows for the old job names are left untouched (log
--     history).

-- 1. Migrate playbook knowledge rows to the skill category.
UPDATE knowledge SET category = 'skill' WHERE category = 'playbook';

-- 2. Remove the playbook_generation LLM node (skills generate directly now).
DELETE FROM memory_llm_configs WHERE task_type = 'playbook_generation';

-- 3. Rename the extraction processed-interactions ledger.
ALTER TABLE playbook_processed_interactions RENAME TO skill_processed_interactions;

-- 4. Drop legacy playbook settings columns.
ALTER TABLE memory_settings
    DROP COLUMN IF EXISTS playbook_schedule_enabled,
    DROP COLUMN IF EXISTS playbook_generation_time,
    DROP COLUMN IF EXISTS playbook_extraction_interval_days,
    DROP COLUMN IF EXISTS playbook_extraction_evidence_threshold;
ALTER TABLE memory_entity_type_config
    DROP COLUMN IF EXISTS playbook_auto_activate;

-- 5. Remove playbook entries from JSON settings (single settings row).
UPDATE memory_settings
SET knowledge_generation_pathway_overrides =
        COALESCE(knowledge_generation_pathway_overrides, '{}'::jsonb) - 'playbook_extraction',
    knowledge_hygiene_category_policies =
        COALESCE(knowledge_hygiene_category_policies, '{}'::jsonb) - 'playbook',
    knowledge_hygiene_enabled_categories =
        COALESCE(knowledge_hygiene_enabled_categories, '[]'::jsonb) - 'playbook'
WHERE id = 1;

-- 6. Entity configs may carry playbook_extraction pathway overrides.
UPDATE memory_entity_type_config
SET knowledge_generation_overrides =
        COALESCE(knowledge_generation_overrides, '{}'::jsonb) - 'playbook_extraction'
WHERE knowledge_generation_overrides ? 'playbook_extraction';
