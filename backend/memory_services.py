"""
memory_services.py — Backward-compatibility shim

All logic now lives in services/ (top-level package).
This file re-exports everything so existing imports continue to work.
"""
from services import (  # noqa: F401
    call_llm,
    call_llm_vision,
    chunk_text,
    extract_entities,
    extract_entities_gliner,
    extract_entities_llm,
    generate_embedding,
    generate_embeddings_batch,
    get_llm_config,
    get_memory_settings,
    get_system_prompt,
    parse_document,
    scrub_pii,
    search_insights_by_vector,
    search_lessons_by_vector,
    search_memories_by_vector,
    summarize_text,
)
