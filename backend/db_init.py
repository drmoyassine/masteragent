"""
db_init.py — Database initialization and seeding

Extracted from server.py to keep the entry point clean.
Contains: init_db(), seed_admin_user(), and the default template seed data.
"""
import json
import uuid
import logging
from datetime import datetime, timezone

from core.auth import hash_password
from core.db import get_db_context

logger = logging.getLogger(__name__)


def init_db():
    """Create all main database tables and run any pending migrations."""
    import sqlite3

    with get_db_context() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                github_id INTEGER UNIQUE,
                username TEXT NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT,
                avatar_url TEXT,
                github_url TEXT,
                github_token TEXT,
                plan TEXT DEFAULT 'free',
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # Settings table (GitHub config per user)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                user_id TEXT,
                github_token TEXT,
                github_repo TEXT,
                github_owner TEXT,
                storage_mode TEXT DEFAULT 'local',
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Migration: Add storage_mode column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE settings ADD COLUMN storage_mode TEXT DEFAULT 'local'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Prompts metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT NOT NULL,
                description TEXT,
                folder_path TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Prompt versions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id TEXT PRIMARY KEY,
                prompt_id TEXT NOT NULL,
                version_name TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (prompt_id) REFERENCES prompts(id)
            )
        """)

        # Templates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                sections TEXT NOT NULL,
                created_at TEXT
            )
        """)

        # API Keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                key_preview TEXT NOT NULL,
                created_at TEXT,
                last_used TEXT
            )
        """)

        # Account-level variables
        cursor.execute("""
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
            )
        """)

        # Prompt-level variables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompt_variables (
                id TEXT PRIMARY KEY,
                prompt_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT 'v1',
                name TEXT NOT NULL,
                value TEXT,
                description TEXT,
                required INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (prompt_id) REFERENCES prompts(id),
                UNIQUE(prompt_id, version, name)
            )
        """)

        # Insert default templates only if table is empty
        cursor.execute("SELECT COUNT(*) FROM templates")
        if cursor.fetchone()[0] == 0:
            _seed_templates(cursor)


def _seed_templates(cursor):
    """Insert the four default prompt templates."""
    now = datetime.now(timezone.utc).isoformat()
    default_templates = [
        {
            "id": str(uuid.uuid4()),
            "name": "Agent Persona",
            "description": "Complete AI agent persona with identity, context, and capabilities",
            "sections": json.dumps([
                {"order": 1, "name": "identity", "title": "Identity", "content": "# Identity\n\nYou are {{agent_name}}, a {{agent_role}}.\n\n## Core Traits\n- Professional and helpful\n- Clear and concise communication\n- Empathetic and understanding"},
                {"order": 2, "name": "context", "title": "Context", "content": "# Context\n\n## Company: {{company_name}}\n\n{{company_description}}\n\n## Your Role\nYou serve as the primary point of contact for {{use_case}}."},
                {"order": 3, "name": "role", "title": "Role & Responsibilities", "content": "# Role & Responsibilities\n\n## Primary Responsibilities\n1. Assist users with their inquiries\n2. Provide accurate information\n3. Escalate complex issues when necessary\n\n## Boundaries\n- Never share confidential information\n- Stay within your area of expertise"},
                {"order": 4, "name": "skills", "title": "Skills & Capabilities", "content": "# Skills & Capabilities\n\n## Core Skills\n- Natural language understanding\n- Context retention\n- Multi-turn conversation\n\n## Tools Available\n{{#tools}}\n- {{name}}: {{description}}\n{{/tools}}"},
                {"order": 5, "name": "guidelines", "title": "Operating Guidelines", "content": "# Operating Guidelines\n\n## Communication Style\n- Tone: {{tone}}\n- Language: {{language}}\n\n## Response Format\n- Keep responses concise but complete\n- Use formatting for clarity\n- Ask clarifying questions when needed"},
            ]),
            "created_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Task Executor",
            "description": "Focused task execution agent with clear instructions",
            "sections": json.dumps([
                {"order": 1, "name": "objective", "title": "Objective", "content": "# Objective\n\nYour primary objective is to {{task_objective}}.\n\n## Success Criteria\n{{success_criteria}}"},
                {"order": 2, "name": "instructions", "title": "Instructions", "content": "# Instructions\n\n## Step-by-Step Process\n1. Analyze the input\n2. Plan your approach\n3. Execute the task\n4. Validate results\n\n## Constraints\n{{constraints}}"},
                {"order": 3, "name": "output", "title": "Output Format", "content": "# Output Format\n\n## Expected Output\n{{output_format}}\n\n## Examples\n{{#examples}}\n### Example {{index}}\nInput: {{input}}\nOutput: {{output}}\n{{/examples}}"},
            ]),
            "created_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Knowledge Expert",
            "description": "Domain-specific knowledge base agent",
            "sections": json.dumps([
                {"order": 1, "name": "domain", "title": "Domain Expertise", "content": "# Domain Expertise\n\nYou are an expert in {{domain}}.\n\n## Knowledge Areas\n{{#knowledge_areas}}\n- {{name}}\n{{/knowledge_areas}}"},
                {"order": 2, "name": "wisdom", "title": "Trade Knowledge", "content": "# Trade Knowledge & Wisdom\n\n## Best Practices\n{{best_practices}}\n\n## Common Pitfalls\n{{common_pitfalls}}\n\n## Lessons Learned\n{{lessons_learned}}"},
                {"order": 3, "name": "responses", "title": "Response Guidelines", "content": "# Response Guidelines\n\n## When answering questions:\n1. Draw from your expertise\n2. Provide practical examples\n3. Cite sources when applicable\n\n## Handling uncertainty:\n- Acknowledge limitations\n- Suggest alternatives\n- Recommend expert consultation when needed"},
            ]),
            "created_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Minimal Prompt",
            "description": "Simple single-section prompt for quick tasks",
            "sections": json.dumps([
                {"order": 1, "name": "prompt", "title": "Main Prompt", "content": "# {{title}}\n\n{{instructions}}\n\n## Input\n{{input}}\n\n## Output\nProvide your response below:"},
            ]),
            "created_at": now,
        },
    ]
    for t in default_templates:
        cursor.execute(
            "INSERT INTO templates (id, name, description, sections, created_at) VALUES (?, ?, ?, ?, ?)",
            (t["id"], t["name"], t["description"], t["sections"], t["created_at"]),
        )


def seed_admin_user():
    """
    Create a default admin user if one doesn't already exist.
    Credentials can be overridden via ADMIN_EMAIL / ADMIN_PASSWORD env vars.
    """
    import os

    if "ADMIN_PASSWORD" not in os.environ:
        logger.warning("Using default admin credentials (admin123). Please set ADMIN_PASSWORD in your .env file!")

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@promptsrc.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
        if not cursor.fetchone():
            now = datetime.now(timezone.utc).isoformat()
            admin_id = str(uuid.uuid4())
            password_hash = hash_password(admin_password)
            cursor.execute(
                """INSERT INTO users (id, username, email, password_hash, plan, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pro', ?, ?)""",
                (admin_id, admin_username, admin_email, password_hash, now, now),
            )
            logger.info(f"Admin user created: {admin_email}")
