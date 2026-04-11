import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_db_context
from config import config

DEFAULT_PROMPTS = [
    {
        "name": "Memory Generation",
        "description": "Generates a factual summary of recent interactions for an entity.",
        "content": (
            "You are an AI memory system. Based on the provided interaction data, write a concise "
            "factual memory record.\n\n"
            "Entity Focus: {{entity.type}} / {{entity.id}}\n"
            "Date: {{date}}\n\n"
            "PRIOR CONTEXT RULES:\n"
            "- Previous memories for this entity are provided under 'Prior Context'.\n"
            "- These represent ESTABLISHED facts. Do NOT repeat them.\n"
            "- Focus EXCLUSIVELY on NEW information from today's interactions.\n"
            "- Note any progressions, status changes, or contradictions with prior records.\n"
            "- If today's interactions contain no new information beyond prior context, "
            "write a brief note stating the interaction occurred with no significant new details.\n\n"
            "OUTPUT RULES:\n"
            "- Return only the summary text, 2-5 sentences.\n"
            "- Focus on key facts, decisions, named entities, and action items."
        )
    },
    {
        "name": "General Summarizer",
        "description": "Summarizes unstructured text.",
        "content": "Summarize this in 1-2 sentences:\n\n{{text}}"
    },
    {
        "name": "Insight Generation",
        "description": "Identifies patterns from prior entity memories.",
        "content": (
            "You are an AI analyst. Based on the provided memory summaries, identify a meaningful pattern, "
            "risk, opportunity, or behavioral insight for {{entity.type}} ({{entity.id}}). Return JSON only: "
            "{\"name\": \"...\", \"insight_type\": \"...\", \"content\": \"...\", \"summary\": \"...\"}"
        )
    },
    {
        "name": "Entity Workspace Assistant",
        "description": "System prompt for the conversational agent in the Workspace.",
        "content": (
            "You are an intelligent assistant helping manage a relationship with {{entity.type}} ({{entity.id}}). "
            "Use the provided memory context to give personalized, accurate answers. "
            "You may suggest creating an insight or updating existing insights by including structured "
            "actions in your reply (see the action syntax instructions appended by the system)."
        )
    }
]

def seed_prompts():
    print("Seeding Memory Prompts into Prompt Manager...")
    admin_id = os.environ.get("ADMIN_USER_ID", "default")
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        
        for p in DEFAULT_PROMPTS:
            # Check if name already exists
            cursor.execute("SELECT id FROM prompts WHERE name = %s", (p["name"],))
            if cursor.fetchone():
                print(f"Prompt '{p['name']}' already exists. Skipping.")
                continue
                
            prompt_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Insert prompt record
            cursor.execute("""
                INSERT INTO prompts (id, name, description, user_id, updated_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (prompt_id, p["name"], p["description"], admin_id, now))
            
            # Extract variables
            import re
            pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}"
            variables = list(set(re.findall(pattern, p["content"])))
            
            # Map into a default version (manifest + sections)
            version_id = f"v{int(now.timestamp())}"
            metadata = {
                "name": "v1",
                "default": True,
                "sections": [{"filename": "system.md", "type": "system", "content": p["content"]}],
                "variables": [{"name": v, "default_value": ""} for v in variables]
            }
            import json
            
            # Create version record
            cursor.execute("""
                INSERT INTO prompt_versions (id, prompt_id, name, is_default, message, metadata_snapshot, content, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (version_id, prompt_id, "v1", True, "Initial seed", json.dumps(metadata), p["content"], now))
            
            print(f"Created Prompt: {p['name']} (Variables: {variables})")
            
        print("Done seeding.")

if __name__ == "__main__":
    seed_prompts()
