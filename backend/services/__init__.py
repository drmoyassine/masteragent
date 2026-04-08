"""
services — Memory system service layer (top-level package)

Kept outside memory/ to avoid circular imports with memory/__init__.py.
All callers should import directly: `from services.llm import call_llm`
or from the backward-compat shim: `from memory_services import call_llm`
"""
from services.config_helpers import get_llm_config, get_memory_settings, get_system_prompt
from services.embeddings import generate_embedding, generate_embeddings_batch
from services.llm import call_llm, call_llm_vision
from services.processing import (
    chunk_text,
    extract_entities,
    extract_entities_gliner,
    extract_entities_llm,
    parse_document,
    scrub_pii,
    summarize_text,
)
from services.search import (
    search_interactions_by_vector,
    search_interactions_by_fulltext,
    search_insights_by_vector,
    search_insights_by_fulltext,
    search_lessons_by_vector,
    search_lessons_by_fulltext,
    search_memories_by_vector,
    search_memories_by_fulltext,
)

__all__ = [
    "get_llm_config", "get_memory_settings", "get_system_prompt",
    "call_llm", "call_llm_vision",
    "generate_embedding", "generate_embeddings_batch",
    "search_interactions_by_vector", "search_interactions_by_fulltext",
    "search_memories_by_vector", "search_memories_by_fulltext",
    "search_insights_by_vector", "search_insights_by_fulltext",
    "search_lessons_by_vector", "search_lessons_by_fulltext",
    "chunk_text", "scrub_pii", "summarize_text", "parse_document",
    "extract_entities", "extract_entities_gliner", "extract_entities_llm",
]
