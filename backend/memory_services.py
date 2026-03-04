# Memory System Services - Processing Pipeline
import os
import uuid
import json
import base64
import httpx
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

from core.storage import get_memory_db_context
from memory_models import RelatedEntity

logger = logging.getLogger(__name__)

# ============================================
# Configuration
# ============================================

GLINER_URL = os.environ.get('GLINER_URL', 'http://localhost:8002')

# ============================================
# Settings & Config Helpers
# ============================================

def get_memory_settings() -> Dict[str, Any]:
    """Get current memory settings"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
    return {}

def get_llm_config(task_type: str) -> Optional[Dict[str, Any]]:
    """
    Get active LLM configuration for a task type.
    Includes fallback logic to share API keys across task types for the same provider.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        # 1. Get the primary active config for this task
        cursor.execute("""
            SELECT * FROM memory_llm_configs
            WHERE task_type = %s AND is_active = TRUE
            ORDER BY updated_at DESC LIMIT 1
        """, (task_type,))
        row = cursor.fetchone()

        if not row:
            return None

        config = dict(row)
        extra = config.get("extra_settings") or {}
        config["extra_config"] = extra if isinstance(extra, dict) else json.loads(extra)

        # 2. Key Fallback: If this config is missing a key, look for one from the same provider
        if not config.get("api_key_encrypted"):
            provider = config.get("provider")
            if provider not in ["gliner", "zendata", "custom"]:
                cursor.execute("""
                    SELECT api_key_encrypted, api_base_url
                    FROM memory_llm_configs
                    WHERE provider = %s AND api_key_encrypted IS NOT NULL AND api_key_encrypted != ''
                    ORDER BY updated_at DESC LIMIT 1
                """, (provider,))
                fallback_row = cursor.fetchone()
                if fallback_row:
                    config["api_key_encrypted"] = fallback_row["api_key_encrypted"]
                    if not config.get("api_base_url") and fallback_row["api_base_url"]:
                        config["api_base_url"] = fallback_row["api_base_url"]
                    logger.info(f"Using inherited API key for {task_type} from provider {provider}")

        return config

def get_system_prompt(prompt_type: str) -> Optional[str]:
    """Get active system prompt by type"""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT prompt_text FROM memory_system_prompts
            WHERE prompt_type = %s AND is_active = TRUE
            ORDER BY updated_at DESC LIMIT 1
        """, (prompt_type,))
        row = cursor.fetchone()
        if row:
            return row["prompt_text"]
    return None

# ============================================
# OpenAI-Compatible LLM Service
# ============================================

def _build_llm_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

async def call_llm(prompt: str, system_prompt: str = None, max_tokens: int = 1000, task_type: str = "summarization") -> str:
    """Call OpenAI-compatible LLM using admin-configured settings"""
    config = get_llm_config(task_type)
    
    if not config or not config.get("api_key_encrypted"):
        logger.warning(f"LLM config for {task_type} not configured or missing API key")
        return ""
    
    api_key = config.get("api_key_encrypted", "")
    api_base = config.get("api_base_url", "https://api.openai.com/v1")
    model = config.get("model_name", "gpt-4o-mini")
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    headers = _build_llm_headers(api_key)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.3
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                logger.error(f"LLM call failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"LLM call error: {e}")
    
    return ""

async def call_llm_vision(prompt: str, image_base64: str, mime_type: str = "image/png") -> str:
    """Call OpenAI-compatible LLM with vision for document parsing"""
    config = get_llm_config("vision")
    
    if not config or not config.get("api_key_encrypted"):
        logger.warning("Vision LLM config not configured or missing API key")
        return ""
    
    api_key = config.get("api_key_encrypted", "")
    api_base = config.get("api_base_url", "https://api.openai.com/v1")
    model = config.get("model_name", "gpt-4o")
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_base64}"
                    }
                }
            ]
        }
    ]
    
    headers = _build_llm_headers(api_key)
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 4000,
                    "temperature": 0.1
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                logger.error(f"Vision LLM call failed: {response.status_code}")
    except Exception as e:
        logger.error(f"Vision LLM call error: {e}")
    
    return ""

# ============================================
# Embedding Service
# ============================================

async def generate_embedding(text: str) -> List[float]:
    """Generate embedding using admin-configured API"""
    config = get_llm_config("embedding")
    
    if not config or not config.get("api_key_encrypted"):
        logger.warning("Embedding config not configured or missing API key")
        return []
    
    api_key = config.get("api_key_encrypted", "")
    api_base = config.get("api_base_url", "https://api.openai.com/v1")
    model = config.get("model_name", "text-embedding-3-small")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base}/embeddings",
                headers=headers,
                json={
                    "model": model,
                    "input": text
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data["data"][0]["embedding"]
            else:
                logger.error(f"Embedding call failed: {response.status_code}")
    except Exception as e:
        logger.error(f"Embedding call error: {e}")
    
    return []

async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts"""
    config = get_llm_config("embedding")
    
    if not config or not config.get("api_key_encrypted") or not texts:
        return []
    
    api_key = config.get("api_key_encrypted", "")
    api_base = config.get("api_base_url", "https://api.openai.com/v1")
    model = config.get("model_name", "text-embedding-3-small")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{api_base}/embeddings",
                headers=headers,
                json={
                    "model": model,
                    "input": texts
                }
            )
            if response.status_code == 200:
                data = response.json()
                return [item["embedding"] for item in data["data"]]
    except Exception as e:
        logger.error(f"Batch embedding error: {e}")
    
    return []

# ============================================
# pgvector Search Service (replaces Qdrant)
# ============================================

async def search_memories_by_vector(
    query_vector: List[float],
    entity_id: str = None,
    entity_type: str = None,
    since: str = None,
    until: str = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Semantic search over the memories table using pgvector cosine distance."""
    if not query_vector:
        return []
    from core.storage import get_memory_db_context as _get_db
    try:
        with _get_db() as conn:
            cursor = conn.cursor()
            conditions = ["embedding IS NOT NULL"]
            params: list = []
            if entity_id:
                conditions.append("primary_entity_id = %s")
                params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s")
                params.append(entity_type)
            if since:
                conditions.append("date >= %s")
                params.append(since)
            if until:
                conditions.append("date <= %s")
                params.append(until)
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, date, primary_entity_type, primary_entity_id,
                       content_summary, related_entities, intents, created_at,
                       1 - (embedding <=> %s::vector) AS score
                FROM memories WHERE {where}
                ORDER BY embedding <=> %s::vector LIMIT %s
            """, params + [query_vector, query_vector, limit])
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector memory search error: {e}")
        return []


async def search_insights_by_vector(
    query_vector: List[float],
    entity_id: str = None,
    entity_type: str = None,
    status: str = "confirmed",
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Semantic search over the insights table."""
    if not query_vector:
        return []
    from core.storage import get_memory_db_context as _get_db
    try:
        with _get_db() as conn:
            cursor = conn.cursor()
            conditions = ["embedding IS NOT NULL"]
            params: list = []
            if entity_id:
                conditions.append("primary_entity_id = %s")
                params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s")
                params.append(entity_type)
            if status:
                conditions.append("status = %s")
                params.append(status)
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, primary_entity_type, primary_entity_id,
                       insight_type, name, summary, status, created_at,
                       1 - (embedding <=> %s::vector) AS score
                FROM insights WHERE {where}
                ORDER BY embedding <=> %s::vector LIMIT %s
            """, params + [query_vector, query_vector, limit])
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector insight search error: {e}")
        return []


async def search_lessons_by_vector(
    query_vector: List[float],
    lesson_type: str = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Semantic search over the lessons table."""
    if not query_vector:
        return []
    from core.storage import get_memory_db_context as _get_db
    try:
        with _get_db() as conn:
            cursor = conn.cursor()
            conditions = ["embedding IS NOT NULL", "visibility = 'shared'"]
            params: list = []
            if lesson_type:
                conditions.append("lesson_type = %s")
                params.append(lesson_type)
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, lesson_type, name, summary, visibility, tags, created_at,
                       1 - (embedding <=> %s::vector) AS score
                FROM lessons WHERE {where}
                ORDER BY embedding <=> %s::vector LIMIT %s
            """, params + [query_vector, query_vector, limit])
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector lesson search error: {e}")
        return []


# Backwards-compatible stubs (no-ops — Qdrant removed)
async def init_qdrant_collections():
    """No-op: vector storage is now pgvector in PostgreSQL."""
    logger.info("pgvector active — Qdrant not used")

async def upsert_vector(collection: str, vector_id: str, vector: List[float], payload: Dict[str, Any]) -> bool:
    """No-op: embeddings stored directly in PostgreSQL VECTOR columns."""
    return True

async def search_vectors(collection: str, query_vector: List[float], filters=None, limit: int = 20) -> List[Dict[str, Any]]:
    """Deprecated stub — use search_*_by_vector() directly."""
    logger.warning("search_vectors() deprecated — use search_memories/insights/lessons_by_vector()")
    return []

async def delete_vector(collection: str, vector_id: str) -> bool:
    """No-op: deletion handled by SQL DELETE on parent table."""
    return True


# ============================================
# PII Scrubbing Service (Admin Configurable)
# ============================================

async def scrub_pii(text: str) -> str:
    """Scrub PII from text using admin-configured service"""
    config = get_llm_config("pii_scrubbing")
    
    if not config or not config.get("api_base_url") or not config.get("api_key_encrypted"):
        logger.warning("PII scrubbing not configured, returning original text")
        return text
    
    api_url = config.get("api_base_url", "")
    api_key = config.get("api_key_encrypted", "")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_url}/redact",
                headers=headers,
                json={"text": text}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("redacted_text", text)
            else:
                logger.error(f"PII scrubbing API error: {response.status_code}")
    except Exception as e:
        logger.error(f"PII scrubbing error: {e}")
    
    return text

# ============================================
# Text Chunking (OpenClaw-style)
# ============================================

def chunk_text(
    text: str,
    chunk_size: int = 400,  # tokens (approx 4 chars per token)
    chunk_overlap: int = 80
) -> List[str]:
    """
    Chunk text using OpenClaw-style algorithm:
    - Target ~400 tokens per chunk with ~80 token overlap
    - Prefer to split on paragraph boundaries, then newline, then sentence
    - Preserve markdown structure
    """
    if not text:
        return []
    
    # Approximate: 1 token ≈ 4 characters
    char_size = chunk_size * 4
    char_overlap = chunk_overlap * 4
    
    if len(text) <= char_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + char_size
        
        if end >= len(text):
            chunks.append(text[start:])
            break
        
        # Try to find a good break point
        chunk = text[start:end]
        
        # Priority: paragraph > newline > sentence > space
        break_point = None
        
        # Look for paragraph break (double newline)
        para_break = chunk.rfind('\n\n')
        if para_break > char_size * 0.5:
            break_point = para_break + 2
        
        # Look for single newline
        if break_point is None:
            newline_break = chunk.rfind('\n')
            if newline_break > char_size * 0.5:
                break_point = newline_break + 1
        
        # Look for sentence end
        if break_point is None:
            for sent_end in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                pos = chunk.rfind(sent_end)
                if pos > char_size * 0.5:
                    break_point = pos + len(sent_end)
                    break
        
        # Fall back to space
        if break_point is None:
            space_break = chunk.rfind(' ')
            if space_break > char_size * 0.3:
                break_point = space_break + 1
        
        # Hard break if nothing found
        if break_point is None:
            break_point = char_size
        
        chunks.append(text[start:start + break_point].strip())
        start = start + break_point - char_overlap
    
    return [c for c in chunks if c.strip()]

# ============================================
# Document Parsing Service
# ============================================

async def parse_document(
    file_content: bytes,
    filename: str,
    mime_type: str
) -> Dict[str, Any]:
    """
    Parse document using LLM vision for images/PDFs
    Returns parsed text and metadata
    """
    result = {
        "text": "",
        "pages": 0,
        "has_images": False,
        "metadata": {}
    }
    
    # For text files, just decode
    if mime_type in ["text/plain", "text/markdown", "text/csv"]:
        try:
            result["text"] = file_content.decode('utf-8')
            return result
        except Exception as e:
            logger.error(f"Failed to decode text file: {e}")
            pass
    
    # For PDFs and images, use vision LLM
    if mime_type in ["application/pdf", "image/png", "image/jpeg", "image/webp", "image/gif"]:
        file_b64 = base64.b64encode(file_content).decode()
        
        prompt = """Extract all text content from this document/image. 
Include:
- All readable text
- Table contents (format as markdown tables)
- Any important visual information described in brackets [like this]
- Preserve the document structure with headings and paragraphs

Output the extracted content as clean markdown:"""
        
        extracted = await call_llm_vision(prompt, file_b64, mime_type)
        if extracted:
            result["text"] = extracted
            result["has_images"] = True
        
        return result
    
    # For DOCX, try basic text extraction
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            from io import BytesIO
            
            with zipfile.ZipFile(BytesIO(file_content)) as zf:
                with zf.open('word/document.xml') as doc:
                    tree = ET.parse(doc)
                    root = tree.getroot()
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    paragraphs = root.findall('.//w:p', ns)
                    text_parts = []
                    for p in paragraphs:
                        texts = p.findall('.//w:t', ns)
                        para_text = ''.join(t.text or '' for t in texts)
                        if para_text:
                            text_parts.append(para_text)
                    result["text"] = '\n\n'.join(text_parts)
        except Exception as e:
            logger.error(f"DOCX parsing error: {e}")
    
    return result

# ============================================
# Summarization Service
# ============================================

async def summarize_text(text: str) -> str:
    """Generate a summary of the text using configured system prompt"""
    if not text:
        return ""
    
    prompt_template = get_system_prompt("summarization")
    if not prompt_template:
        prompt_template = "Summarize this in 1-2 sentences:\n\n{text}"
    
    prompt = prompt_template.replace("{text}", text[:4000])  # Limit input
    return await call_llm(prompt, max_tokens=200, task_type="summarization")

# ============================================
# Entity Extraction Service (GLiNER or LLM)
# ============================================

async def extract_entities_gliner(text: str, confidence_threshold: float = 0.5) -> dict:
    """Extract entities using GLiNER2 NER service"""
    config = get_llm_config("entity_extraction")

    if not config or config.get("provider") != "gliner":
        return {"entities": [], "intents": [], "relationships": []}

    gliner_url = config.get("api_base_url", GLINER_URL)
    # Use passed threshold, but allow DB config to override it
    extra_config = config.get("extra_config", {})
    threshold = extra_config.get("threshold", confidence_threshold)

    labels = ["person", "organization", "location", "product", "event", "date"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{gliner_url}/extract",
                json={
                    "text": text[:4000],
                    "labels": labels,
                    "threshold": threshold
                }
            )
            if response.status_code == 200:
                data = response.json()
                entities = []
                for e in data.get("entities", []):
                    entity_type = "contact" if e.get("label") == "person" else (
                        "institution" if e.get("label") == "organization" else "program"
                    )
                    entities.append({
                        "entity_id": str(uuid.uuid4()),
                        "entity_type": entity_type,
                        "name": e.get("text", ""),
                        "role": "mentioned",
                        "score": e.get("score", 0),
                    })
                return {"entities": entities, "intents": [], "relationships": []}
            else:
                logger.error(f"GLiNER extraction failed: {response.status_code}")
    except Exception as e:
        logger.error(f"GLiNER extraction error: {e}")

    return {"entities": [], "intents": [], "relationships": []}


async def extract_entities_llm(text: str, confidence_threshold: float = 0.5) -> dict:
    """Extract entities using LLM"""
    prompt_template = get_system_prompt("entity_extraction")
    if not prompt_template:
        return {"entities": [], "intents": [], "relationships": []}

    response = await call_llm(text[:4000], system_prompt=prompt_template, max_tokens=500, task_type="summarization")

    try:
        parsed = json.loads(response)
        if isinstance(parsed, list):
            return {"entities": parsed, "intents": [], "relationships": []}
    except Exception as e:
        logger.error(f"Failed to parse entity extraction LLM response: {e}")

    return {"entities": [], "intents": [], "relationships": []}


async def extract_entities(text: str, confidence_threshold: float = 0.5) -> dict:
    """
    Extract entity mentions from text using configured extractor.
    Returns dict: {entities: [...], intents: [...], relationships: [...]}
    """
    if not text:
        return {"entities": [], "intents": [], "relationships": []}

    config = get_llm_config("entity_extraction")

    if config and config.get("provider") == "gliner":
        return await extract_entities_gliner(text, confidence_threshold=confidence_threshold)
    else:
        return await extract_entities_llm(text, confidence_threshold=confidence_threshold)

