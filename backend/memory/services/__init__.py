"""
memory/services — Memory system service layer

Public API: import from here or from the individual sub-modules directly.
"""
from memory.services.config_helpers import get_llm_config, get_memory_settings, get_system_prompt
from memory.services.embeddings import generate_embedding, generate_embeddings_batch
from memory.services.llm import call_llm, call_llm_vision
from memory.services.processing import (
    chunk_text,
    extract_entities,
    extract_entities_gliner,
    extract_entities_llm,
    parse_document,
    scrub_pii,
    summarize_text,
)
from memory.services.search import (
    search_insights_by_vector,
    search_lessons_by_vector,
    search_memories_by_vector,
)

__all__ = [
    # config
    "get_llm_config",
    "get_memory_settings",
    "get_system_prompt",
    # llm
    "call_llm",
    "call_llm_vision",
    # embeddings
    "generate_embedding",
    "generate_embeddings_batch",
    # search
    "search_memories_by_vector",
    "search_insights_by_vector",
    "search_lessons_by_vector",
    # processing
    "chunk_text",
    "scrub_pii",
    "summarize_text",
    "parse_document",
    "extract_entities",
    "extract_entities_gliner",
    "extract_entities_llm",
]
