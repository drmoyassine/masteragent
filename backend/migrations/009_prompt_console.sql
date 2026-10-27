-- Migration 009: create the prompt-console tables on fresh installs.
--
-- TASK-257 §3 phase-2 removed the prompt-console DDL from db_init.init_db()
-- and no migration replaced it, so a fresh database booted with users + the
-- memory schema but WITHOUT settings, prompts, prompt_versions, pm_files,
-- templates, api_keys, account_variables, prompt_variables — every
-- prompt-manager route 500'd (first seen on a fresh benchmark deploy,
-- 2026-10-26: psycopg2 UndefinedTable "relation \"api_keys\" does not exist").
-- Legacy deployments already carry these tables from the pre-freeze boot DDL;
-- every statement is IF NOT EXISTS / empty-guarded so they no-op.
--
-- DDL is verbatim from the pre-§3 init_db() (see 1d5bfb9^); column shapes are
-- frozen by the live routes (routes/{prompts,templates,variables,api_keys}.py).

CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    github_token TEXT,
    github_repo TEXT,
    github_owner TEXT,
    storage_mode TEXT DEFAULT 'local',
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
ALTER TABLE settings ADD COLUMN IF NOT EXISTS storage_mode TEXT DEFAULT 'local';

CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    folder_path TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL,
    version_name TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TEXT,
    FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);

-- Prompt engine file store (zero-git mode): every editor "file"
-- (manifest.json, NN_section.md) is a row keyed by path+version+name.
CREATE TABLE IF NOT EXISTS pm_files (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    folder_path TEXT NOT NULL,
    version TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (folder_path, version, filename)
);
CREATE INDEX IF NOT EXISTS idx_pm_files_path_version ON pm_files (folder_path, version);

CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    sections TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    key_preview TEXT NOT NULL,
    created_at TEXT,
    last_used TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS user_id TEXT REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys (user_id);

CREATE TABLE IF NOT EXISTS account_variables (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT,
    description TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS prompt_variables (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT 'v1',
    name TEXT NOT NULL,
    value TEXT,
    description TEXT,
    required BOOLEAN DEFAULT FALSE,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (prompt_id) REFERENCES prompts(id),
    UNIQUE(prompt_id, version, name)
);

-- Default template library (pre-§3 fresh installs seeded these at boot;
-- sections JSON is byte-identical to the old _seed_templates). Static ids so
-- re-runs are deterministic; the NOT EXISTS guard keeps legacy installs (or
-- admins who deleted the defaults) untouched.
INSERT INTO templates (id, name, description, sections, created_at)
SELECT s.id, s.name, s.description, s.sections, now()::text
FROM (VALUES
  ('4d1a2f60-0000-4000-8000-0000000000c1', 'Agent Persona', 'Complete AI agent persona with identity, context, and capabilities', '[{"order": 1, "name": "identity", "title": "Identity", "content": "# Identity\n\nYou are {{agent_name}}, a {{agent_role}}.\n\n## Core Traits\n- Professional and helpful\n- Clear and concise communication\n- Empathetic and understanding"}, {"order": 2, "name": "context", "title": "Context", "content": "# Context\n\n## Company: {{company_name}}\n\n{{company_description}}\n\n## Your Role\nYou serve as the primary point of contact for {{use_case}}."}, {"order": 3, "name": "role", "title": "Role & Responsibilities", "content": "# Role & Responsibilities\n\n## Primary Responsibilities\n1. Assist users with their inquiries\n2. Provide accurate information\n3. Escalate complex issues when necessary\n\n## Boundaries\n- Never share confidential information\n- Stay within your area of expertise"}, {"order": 4, "name": "skills", "title": "Skills & Capabilities", "content": "# Skills & Capabilities\n\n## Core Skills\n- Natural language understanding\n- Context retention\n- Multi-turn conversation\n\n## Tools Available\n{{#tools}}\n- {{name}}: {{description}}\n{{/tools}}"}, {"order": 5, "name": "guidelines", "title": "Operating Guidelines", "content": "# Operating Guidelines\n\n## Communication Style\n- Tone: {{tone}}\n- Language: {{language}}\n\n## Response Format\n- Keep responses concise but complete\n- Use formatting for clarity\n- Ask clarifying questions when needed"}]'),
  ('4d1a2f60-0000-4000-8000-0000000000c2', 'Task Executor', 'Focused task execution agent with clear instructions', '[{"order": 1, "name": "objective", "title": "Objective", "content": "# Objective\n\nYour primary objective is to {{task_objective}}.\n\n## Success Criteria\n{{success_criteria}}"}, {"order": 2, "name": "instructions", "title": "Instructions", "content": "# Instructions\n\n## Step-by-Step Process\n1. Analyze the input\n2. Plan your approach\n3. Execute the task\n4. Validate results\n\n## Constraints\n{{constraints}}"}, {"order": 3, "name": "output", "title": "Output Format", "content": "# Output Format\n\n## Expected Output\n{{output_format}}\n\n## Examples\n{{#examples}}\n### Example {{index}}\nInput: {{input}}\nOutput: {{output}}\n{{/examples}}"}]'),
  ('4d1a2f60-0000-4000-8000-0000000000c3', 'Knowledge Expert', 'Domain-specific knowledge base agent', '[{"order": 1, "name": "domain", "title": "Domain Expertise", "content": "# Domain Expertise\n\nYou are an expert in {{domain}}.\n\n## Knowledge Areas\n{{#knowledge_areas}}\n- {{name}}\n{{/knowledge_areas}}"}, {"order": 2, "name": "wisdom", "title": "Trade Knowledge", "content": "# Trade Knowledge & Wisdom\n\n## Best Practices\n{{best_practices}}\n\n## Common Pitfalls\n{{common_pitfalls}}\n\n## Lessons Learned\n{{lessons_learned}}"}, {"order": 3, "name": "responses", "title": "Response Guidelines", "content": "# Response Guidelines\n\n## When answering questions:\n1. Draw from your expertise\n2. Provide practical examples\n3. Cite sources when applicable\n\n## Handling uncertainty:\n- Acknowledge limitations\n- Suggest alternatives\n- Recommend expert consultation when needed"}]'),
  ('4d1a2f60-0000-4000-8000-0000000000c4', 'Minimal Prompt', 'Simple single-section prompt for quick tasks', '[{"order": 1, "name": "prompt", "title": "Main Prompt", "content": "# {{title}}\n\n{{instructions}}\n\n## Input\n{{input}}\n\n## Output\nProvide your response below:"}]')
) AS s(id, name, description, sections)
WHERE NOT EXISTS (SELECT 1 FROM templates);
