# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview
MasterAgent (PromptSRC) - Full-stack AI agent infrastructure with prompt management and memory system.

## Critical Architecture Notes

### Dual Database System
- **Main DB**: `backend/prompt_manager.db` - Users, prompts, settings, API keys
- **Memory DB**: `backend/data/memory.db` - Entity types, interactions, lessons, agents
- Use `get_db_context()` for main DB, `get_memory_db_context()` for memory DB

### Dual Authentication
- **JWT (Bearer token)**: Admin/config endpoints - via `require_admin_auth()`
- **API Key (X-API-Key header)**: Agent-facing endpoints - via `verify_agent_key()`

### Service Ports
- Backend: 8001 (Docker), 8000 (local dev)
- GLiNER NER: 8002
- Qdrant: 6333 (REST), 6334 (gRPC)

## Build Commands
```bash
# Frontend (uses yarn + craco)
cd frontend && yarn install && yarn build
# Backend
cd backend && pip install -r requirements.txt
# Docker (production)
docker-compose up --build
```

## Test Commands
```bash
# Run all backend tests
cd backend && pytest tests/ -v
# Run specific test file
pytest tests/test_memory_auth.py -v
# Run with environment override
REACT_APP_BACKEND_URL=http://localhost pytest tests/
```

## Key Patterns
- Frontend path alias: `@/` maps to `frontend/src/`
- Memory router prefix: `/api/memory`
- LLM configs keyed by `task_type` (summarization, embedding, vision, entity_extraction, pii_scrubbing)
- Test credentials: `admin@promptsrc.com` / `admin123`
