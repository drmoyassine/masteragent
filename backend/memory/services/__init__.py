"""
memory/services — DEPRECATED sub-package stub.

All service logic has been moved to the top-level `services/` package
to avoid circular imports with memory/__init__.py.

This __init__.py re-exports everything for any code that still imports
from `memory.services` directly (e.g., during transition).
"""
from services import *  # noqa: F401, F403
from services import (  # noqa: F401
    call_llm, call_llm_vision,
    chunk_text, extract_entities, extract_entities_gliner, extract_entities_llm,
    generate_embedding, generate_embeddings_batch,
    get_llm_config, get_memory_settings, get_system_prompt,
    parse_document, scrub_pii,
    search_intelligence_by_vector, search_knowledge_by_vector, search_memories_by_vector,
    summarize_text,
)
