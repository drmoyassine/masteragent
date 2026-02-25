# Memory System Database Schema and Initialization
import sqlite3
import os
import json
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

# Database configuration
DATABASE_TYPE = os.environ.get('DATABASE_TYPE', 'sqlite')
DATABASE_PATH = Path(__file__).parent / "data" / "memory.db"

def get_memory_db():
    """Get database connection"""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_memory_db_context():
    conn = get_memory_db()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_memory_db():
    """Initialize memory system database tables"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # ============================================
        # Configuration Tables
        # ============================================
        
        # Entity Types (Contact, Organization, Project, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entity_types (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                icon TEXT DEFAULT 'folder',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # Entity Subtypes (Lead, Partner, Internal, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entity_subtypes (
                id TEXT PRIMARY KEY,
                entity_type_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT,
                FOREIGN KEY (entity_type_id) REFERENCES memory_entity_types(id) ON DELETE CASCADE,
                UNIQUE(entity_type_id, name)
            )
        """)
        
        # Lesson Types (Process, Risk, Sales, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_lesson_types (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                color TEXT DEFAULT '#22C55E',
                created_at TEXT
            )
        """)
        
        # Channel Types (email, call, meeting, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_channel_types (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                icon TEXT DEFAULT 'message-circle',
                created_at TEXT
            )
        """)
        
        # Registered Agents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                api_key_hash TEXT NOT NULL,
                api_key_preview TEXT NOT NULL,
                access_level TEXT DEFAULT 'private',
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                last_used TEXT
            )
        """)
        
        # System Prompts for LLM operations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_system_prompts (
                id TEXT PRIMARY KEY,
                prompt_type TEXT NOT NULL,
                name TEXT NOT NULL,
                prompt_text TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # Memory System Settings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                chunk_size INTEGER DEFAULT 400,
                chunk_overlap INTEGER DEFAULT 80,
                auto_lesson_enabled INTEGER DEFAULT 1,
                auto_lesson_threshold INTEGER DEFAULT 5,
                lesson_approval_required INTEGER DEFAULT 1,
                pii_scrubbing_enabled INTEGER DEFAULT 1,
                auto_share_scrubbed INTEGER DEFAULT 0,
                openclaw_sync_enabled INTEGER DEFAULT 0,
                openclaw_sync_path TEXT DEFAULT '',
                openclaw_sync_type TEXT DEFAULT 'filesystem',
                openclaw_sync_frequency INTEGER DEFAULT 5,
                rate_limit_enabled INTEGER DEFAULT 0,
                rate_limit_per_minute INTEGER DEFAULT 60,
                default_agent_access TEXT DEFAULT 'private',
                updated_at TEXT
            )
        """)
        
        # ============================================
        # Memory Tables (Private)
        # ============================================
        
        # Main Memories Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                timestamp TEXT NOT NULL,
                channel TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                summary_text TEXT,
                has_documents INTEGER DEFAULT 0,
                is_shared INTEGER DEFAULT 0,
                entities_json TEXT DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}',
                vector_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # Memory Documents (parsed attachments)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_documents (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT,
                file_size INTEGER,
                parsed_text TEXT,
                chunk_count INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)
        
        # Document Chunks (for vector storage reference)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_document_chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                vector_id TEXT,
                created_at TEXT,
                FOREIGN KEY (document_id) REFERENCES memory_documents(id) ON DELETE CASCADE
            )
        """)
        
        # Lessons Table (Private)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_lessons (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                lesson_type TEXT NOT NULL,
                name TEXT NOT NULL,
                body TEXT NOT NULL,
                summary TEXT,
                status TEXT DEFAULT 'draft',
                is_shared INTEGER DEFAULT 0,
                related_entities_json TEXT DEFAULT '[]',
                source_memory_ids_json TEXT DEFAULT '[]',
                vector_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # ============================================
        # Shared Memory Tables (PII-Stripped)
        # ============================================
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories_shared (
                id TEXT PRIMARY KEY,
                original_memory_id TEXT NOT NULL,
                pii_stripped_text TEXT NOT NULL,
                summary_text TEXT,
                channel TEXT NOT NULL,
                entities_json TEXT DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}',
                vector_id TEXT,
                created_at TEXT,
                FOREIGN KEY (original_memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_lessons_shared (
                id TEXT PRIMARY KEY,
                original_lesson_id TEXT NOT NULL,
                lesson_type TEXT NOT NULL,
                name TEXT NOT NULL,
                pii_stripped_body TEXT NOT NULL,
                summary TEXT,
                related_entities_json TEXT DEFAULT '[]',
                vector_id TEXT,
                created_at TEXT,
                FOREIGN KEY (original_lesson_id) REFERENCES memory_lessons(id) ON DELETE CASCADE
            )
        """)
        
        # ============================================
        # Audit Log
        # ============================================
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_audit_log (
                id TEXT PRIMARY KEY,
                agent_id TEXT,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                details_json TEXT DEFAULT '{}',
                timestamp TEXT NOT NULL
            )
        """)
        
        # ============================================
        # Indexes for performance
        # ============================================
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_channel ON memories(channel)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lessons_type ON memory_lessons(lesson_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lessons_status ON memory_lessons(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON memory_audit_log(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent ON memory_audit_log(agent_id)")
        
        # ============================================
        # Seed Default Data
        # ============================================
        
        # Default settings
        cursor.execute("SELECT id FROM memory_settings WHERE id = 1")
        if not cursor.fetchone():
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO memory_settings (id, updated_at) VALUES (1, ?)
            """, (now,))
        
        # Default entity types
        default_entity_types = [
            ("Contact", "People you interact with", "user"),
            ("Organization", "Companies and institutions", "building"),
            ("Program", "Projects and initiatives", "folder-kanban"),
        ]
        for name, desc, icon in default_entity_types:
            cursor.execute("SELECT id FROM memory_entity_types WHERE name = ?", (name,))
            if not cursor.fetchone():
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO memory_entity_types (id, name, description, icon, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), name, desc, icon, now, now))
        
        # Default subtypes for Contact
        cursor.execute("SELECT id FROM memory_entity_types WHERE name = 'Contact'")
        contact_type = cursor.fetchone()
        if contact_type:
            default_subtypes = ["Lead", "Partner", "Provider", "Internal", "Other"]
            for subtype in default_subtypes:
                cursor.execute("""
                    SELECT id FROM memory_entity_subtypes 
                    WHERE entity_type_id = ? AND name = ?
                """, (contact_type["id"], subtype))
                if not cursor.fetchone():
                    now = datetime.now(timezone.utc).isoformat()
                    cursor.execute("""
                        INSERT INTO memory_entity_subtypes (id, entity_type_id, name, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (str(uuid.uuid4()), contact_type["id"], subtype, now))
        
        # Default subtypes for Organization
        cursor.execute("SELECT id FROM memory_entity_types WHERE name = 'Organization'")
        org_type = cursor.fetchone()
        if org_type:
            default_subtypes = ["Institution", "Partner", "Provider", "School", "Internal", "Other"]
            for subtype in default_subtypes:
                cursor.execute("""
                    SELECT id FROM memory_entity_subtypes 
                    WHERE entity_type_id = ? AND name = ?
                """, (org_type["id"], subtype))
                if not cursor.fetchone():
                    now = datetime.now(timezone.utc).isoformat()
                    cursor.execute("""
                        INSERT INTO memory_entity_subtypes (id, entity_type_id, name, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (str(uuid.uuid4()), org_type["id"], subtype, now))
        
        # Default lesson types
        default_lesson_types = [
            ("Process", "Workflow and process improvements", "#22C55E"),
            ("Risk", "Risk identification and mitigation", "#EF4444"),
            ("Sales", "Sales insights and strategies", "#3B82F6"),
            ("Product", "Product feedback and ideas", "#8B5CF6"),
            ("Support", "Customer support learnings", "#F59E0B"),
            ("Other", "Miscellaneous learnings", "#6B7280"),
        ]
        for name, desc, color in default_lesson_types:
            cursor.execute("SELECT id FROM memory_lesson_types WHERE name = ?", (name,))
            if not cursor.fetchone():
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO memory_lesson_types (id, name, description, color, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), name, desc, color, now))
        
        # Default channel types
        default_channels = [
            ("email", "Email correspondence", "mail"),
            ("call", "Phone or video calls", "phone"),
            ("meeting", "In-person or virtual meetings", "users"),
            ("chat", "Chat or messaging", "message-circle"),
            ("document", "Document upload or review", "file-text"),
            ("note", "Manual notes", "sticky-note"),
        ]
        for name, desc, icon in default_channels:
            cursor.execute("SELECT id FROM memory_channel_types WHERE name = ?", (name,))
            if not cursor.fetchone():
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO memory_channel_types (id, name, description, icon, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), name, desc, icon, now))
        
        # Default system prompts
        default_prompts = [
            ("summarization", "Default Summarizer", """Summarize the following interaction in 1-2 concise sentences. Focus on the key points, decisions, and action items.

Interaction:
{text}

Summary:"""),
            ("lesson_extraction", "Default Lesson Extractor", """Analyze the following interactions and extract a lesson learned. The lesson should be actionable and generalizable.

Interactions:
{interactions}

Provide:
1. A short lesson name (5-10 words)
2. The lesson type (Process, Risk, Sales, Product, Support, or Other)
3. A detailed lesson body in Markdown format (2-3 paragraphs)

Format your response as JSON:
{{"name": "...", "type": "...", "body": "..."}}"""),
            ("entity_extraction", "Default Entity Extractor", """Extract any mentioned entities from the following text. Look for people, organizations, and projects/programs.

Text:
{text}

Return a JSON array of entities:
[{{"type": "Contact|Organization|Program", "name": "...", "role": "primary|mentioned|cc"}}]"""),
        ]
        for prompt_type, name, prompt_text in default_prompts:
            cursor.execute("""
                SELECT id FROM memory_system_prompts 
                WHERE prompt_type = ? AND is_active = 1
            """, (prompt_type,))
            if not cursor.fetchone():
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO memory_system_prompts (id, prompt_type, name, prompt_text, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                """, (str(uuid.uuid4()), prompt_type, name, prompt_text, now, now))

# Initialize on import
init_memory_db()
