"""services/processing.py — Text chunking, summarization, PII scrubbing, document parsing, entity extraction"""
import base64
import json
import logging
import os
import uuid
from typing import Any, Dict, List

import httpx

from services.config_helpers import get_llm_config, get_system_prompt
from services.llm import call_llm, call_llm_vision

logger = logging.getLogger(__name__)

GLINER_URL = os.environ.get("GLINER_URL", "http://localhost:8002")
_EMPTY_EXTRACTION: Dict[str, List] = {"entities": [], "intents": [], "relationships": []}


# ── Text Chunking ──────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 400, chunk_overlap: int = 80) -> List[str]:
    """
    Chunk text using OpenClaw-style algorithm.
    chunk_size / chunk_overlap are in tokens (≈4 chars per token).
    Splits on paragraph > newline > sentence > space.
    """
    if not text:
        return []
    char_size = chunk_size * 4
    char_overlap = chunk_overlap * 4
    if len(text) <= char_size:
        return [text]

    chunks, start = [], 0
    while start < len(text):
        end = start + char_size
        if end >= len(text):
            chunks.append(text[start:])
            break
        chunk = text[start:end]
        break_point = None
        para = chunk.rfind("\n\n")
        if para > char_size * 0.5:
            break_point = para + 2
        if break_point is None:
            nl = chunk.rfind("\n")
            if nl > char_size * 0.5:
                break_point = nl + 1
        if break_point is None:
            for marker in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
                pos = chunk.rfind(marker)
                if pos > char_size * 0.5:
                    break_point = pos + len(marker)
                    break
        if break_point is None:
            sp = chunk.rfind(" ")
            if sp > char_size * 0.3:
                break_point = sp + 1
        if break_point is None:
            break_point = char_size
        chunks.append(text[start: start + break_point].strip())
        start = start + break_point - char_overlap
    return [c for c in chunks if c.strip()]


# ── PII Scrubbing ──────────────────────────────────────────────────────────────

async def scrub_pii(text: str) -> str:
    """Scrub PII from text using admin-configured service. Returns original text on failure."""
    config = get_llm_config("pii_scrubbing")
    if not config or not config.get("api_base_url") or not config.get("api_key_encrypted"):
        logger.warning("PII scrubbing not configured, returning original text")
        return text
    headers = {
        "Authorization": f"Bearer {config['api_key_encrypted']}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{config['api_base_url']}/redact", headers=headers, json={"text": text}
            )
            if response.status_code == 200:
                return response.json().get("redacted_text", text)
            logger.error(f"PII scrubbing API error: {response.status_code}")
    except Exception as e:
        logger.error(f"PII scrubbing error: {e}")
    return text


# ── Summarization ──────────────────────────────────────────────────────────────

async def summarize_text(text: str) -> str:
    """Generate a short summary of text using configured system prompt."""
    if not text:
        return ""
    prompt_template = get_system_prompt("summarization") or "Summarize this in 1-2 sentences:\n\n{text}"
    prompt = prompt_template.replace("{text}", text[:4000])
    return await call_llm(prompt, max_tokens=200, task_type="summarization")


# ── Document Parsing ───────────────────────────────────────────────────────────

async def parse_document(file_content: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
    """Parse a document (text, PDF, image, DOCX) into text + metadata."""
    result: Dict[str, Any] = {"text": "", "pages": 0, "has_images": False, "metadata": {}}

    if mime_type in ("text/plain", "text/markdown", "text/csv"):
        try:
            result["text"] = file_content.decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to decode text file: {e}")
        return result

    if mime_type in ("application/pdf", "image/png", "image/jpeg", "image/webp", "image/gif"):
        file_b64 = base64.b64encode(file_content).decode()
        prompt = (
            "Extract all text content from this document/image. "
            "Include all readable text, table contents (as markdown tables), "
            "and important visual information in [brackets]. Preserve structure.\n\nOutput as clean markdown:"
        )
        extracted = await call_llm_vision(prompt, file_b64, mime_type)
        if extracted:
            result["text"] = extracted
            result["has_images"] = True
        return result

    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            from io import BytesIO
            with zipfile.ZipFile(BytesIO(file_content)) as zf:
                with zf.open("word/document.xml") as doc:
                    root = ET.parse(doc).getroot()
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    parts = [
                        "".join(t.text or "" for t in p.findall(".//w:t", ns))
                        for p in root.findall(".//w:p", ns)
                    ]
                    result["text"] = "\n\n".join(p for p in parts if p)
        except Exception as e:
            logger.error(f"DOCX parsing error: {e}")
    return result


# ── Entity Extraction ──────────────────────────────────────────────────────────

DEFAULT_NER_LABELS = ["person", "organization", "location", "product", "event", "date"]


async def extract_entities_gliner(text: str, confidence_threshold: float = 0.5, ner_schema: dict = None) -> dict:
    """Extract entities using GLiNER NER service."""
    config = get_llm_config("entity_extraction")
    if not config or config.get("provider") != "gliner":
        return _EMPTY_EXTRACTION

    gliner_url = config.get("api_base_url", GLINER_URL)
    threshold = config.get("extra_config", {}).get("threshold", confidence_threshold)
    labels = (
        ner_schema.get("labels", DEFAULT_NER_LABELS)
        if ner_schema else DEFAULT_NER_LABELS
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{gliner_url}/extract",
                json={"text": text[:4000], "labels": labels, "threshold": threshold},
            )
            if response.status_code == 200:
                entities = []
                for e in response.json().get("entities", []):
                    label = e.get("label", "")
                    entity_type = "contact" if label == "person" else (
                        "institution" if label == "organization" else "program"
                    )
                    entities.append({
                        "entity_id": str(uuid.uuid4()),
                        "entity_type": entity_type,
                        "name": e.get("text", ""),
                        "role": "mentioned",
                        "score": e.get("score", 0),
                    })
                return {"entities": entities, "intents": [], "relationships": []}
            logger.error(f"GLiNER extraction failed: {response.status_code}")
    except Exception as e:
        logger.error(f"GLiNER extraction error: {e}")
    return _EMPTY_EXTRACTION


async def extract_entities_llm(text: str, confidence_threshold: float = 0.5, ner_schema: dict = None) -> dict:
    """Extract entities using LLM fallback."""
    prompt_template = get_system_prompt("entity_extraction")
    if not prompt_template:
        return _EMPTY_EXTRACTION
    if ner_schema and ner_schema.get("labels"):
        labels_str = ", ".join(ner_schema["labels"])
        prompt_template = (
            f"Extract named entities from the text. Focus only on these types: {labels_str}.\n"
            "Return a JSON array: [{\"entity_id\": \"uuid\", \"entity_type\": \"...\", "
            "\"name\": \"...\", \"role\": \"...\"}]"
        )
    response = await call_llm(
        text[:4000], system_prompt=prompt_template, max_tokens=500, task_type="entity_extraction"
    )
    try:
        parsed = json.loads(response)
        if isinstance(parsed, list):
            return {"entities": parsed, "intents": [], "relationships": []}
    except Exception as e:
        logger.error(f"Failed to parse entity extraction LLM response: {e}")
    return _EMPTY_EXTRACTION


async def extract_entities(text: str, confidence_threshold: float = 0.5, ner_schema: dict = None) -> dict:
    """
    Extract entity mentions from text using configured extractor (GLiNER or LLM).
    Pass ner_schema to constrain extraction to specific labels.
    Returns dict: {entities: [...], intents: [...], relationships: [...]}
    """
    if not text:
        return _EMPTY_EXTRACTION
    config = get_llm_config("entity_extraction")
    if config and config.get("provider") == "gliner":
        return await extract_entities_gliner(text, confidence_threshold=confidence_threshold, ner_schema=ner_schema)
    return await extract_entities_llm(text, confidence_threshold=confidence_threshold, ner_schema=ner_schema)
