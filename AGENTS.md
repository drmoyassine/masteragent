# AGENTS.md

This file provides guidance to AI agents working with this repository.

## Project Overview

**MasterAgent** — Full-stack AI agent infrastructure providing:
1. **Prompt Manager** — Git-backed version-controlled AI prompts, consumed via API
2. **Memory System** — 4-tier persistent memory (Interactions → Memories → Insights → Lessons) with pgvector semantic search

## Architecture Quick Reference

### Single PostgreSQL Database
Both modules share one PostgreSQL 16 + pgvector instance:
- Use `core.db.get_db_context()` for Prompt Manager tables
- Use `core.storage.get_memory_db_context()` for Memory System tables
- Connection resolved via: `DATABASE_URL` → `MEMORY_POSTGRES_URL` → default `postgres:5432`

### Dual Authentication
- **JWT (Bearer token)**: Admin/config endpoints — `memory.auth.require_admin_auth()`, `core.auth.require_admin_auth()`
- **API Key (X-API-Key header)**: Agent-facing endpoints — `core.auth.verify_agent_key()`
- **HMAC-SHA256**: Webhook inbound validation (inline in `memory/webhooks.py`)

### Service Ports (Local Dev)
- Backend: `8084` (local), `8001` (Docker internal)
- PostgreSQL: `5432`
- Redis: `6379`
- GLiNER NER: `8002` (optional Docker profile)

### Key Packages
```
backend/
├── core/           # Shared DB, auth, storage utilities
├── routes/         # Prompt Manager endpoints
├── memory/         # Memory System (routers + logic)
├── services/       # Infrastructure services (LLM, embeddings, search, processing)
│                   # Top-level to avoid circular imports with memory/
├── server.py       # FastAPI entry point
├── memory_db.py    # Memory schema + migrations
├── db_init.py      # Prompt Manager schema
└── memory_services.py  # Backward-compat shim → services/
```

## Build & Run Commands

```bash
# Backend (local)
cd backend
pip install -r requirements.txt
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/memory"
$env:MEMORY_POSTGRES_URL="postgresql://postgres:postgres@localhost:5432/memory"
$env:REDIS_URL="redis://localhost:6379"
python -m uvicorn server:app --port 8084

# Frontend (local)
cd frontend
yarn install
yarn start

# Docker (production)
docker compose up -d

# Docker with GLiNER
docker compose --profile gliner up -d
```

## Test Commands

```bash
# Requires running server at MEMORY_TEST_BASE_URL
cd backend/tests
$env:MEMORY_TEST_BASE_URL="http://localhost:8084"
python -m pytest . -v --timeout=30
# Expected: 101 passed, 2 skipped (LLM key required)
```

## Key Patterns & Conventions

### PowerShell (Windows Environment)
> **CRITICAL**: User runs PowerShell 7. Always use PowerShell syntax.

| Unix/Bash | PowerShell |
|-----------|------------|
| `&&` | `;` |
| `2>/dev/null` | `2>$null` |
| `grep` | `Select-String` |
| `cat` | `Get-Content` |
| `export VAR=val` | `$env:VAR="val"` |

### Memory Router Prefix
All memory endpoints: `/api/memory/*`
- Admin stats live at: `/api/memory/admin/stats` and `/api/memory/admin/stats/agents`
- These are defined in `memory/admin.py` with `/admin/stats` and `/admin/stats/agents` path decorators (not via router prefix)

### LLM Config Task Types
LLM configs are keyed by `task_type`:
- `summarization`, `embedding`, `vision`, `entity_extraction`, `pii_scrubbing`

### Frontend Conventions
- Path alias: `@/` → `frontend/src/`
- API client: `frontend/src/lib/api.js`
- Storage mode: `ConfigContext.jsx` (`github` vs `local`)
- Version references: read `is_default` from API — never hardcode `"v1"` or `"main"`

### Storage Service Pattern
- `get_storage_service()` factory in `storage_service.py`
- Returns `GitHubStorageService` if `github_token` configured, else `LocalStorageService`
- Local fallback: `backend/local_prompts/{user_id}/`

### Docker Volume Persistence
Named volumes in `docker-compose.yml`:
- `promptsrc_db` → `/app/backend/db/`
- `promptsrc_prompts` → `/app/backend/local_prompts/`
- `postgres_data` → PostgreSQL data directory
- `redis_data` → Redis AOF persistence

### Admin Credentials (Default)
```
Email:    set via ADMIN_EMAIL env var
Password: set via ADMIN_PASSWORD env var
Default:  admin@masteragent.ai / change_me_in_production
```

## Related Documentation
- `ARCHITECTURE.md` — Full system architecture
- `HANDOFF.md` — Session history and current project state
- `memory/PRD.md` — Memory system product requirements
- `.env.example` — Full environment variable reference
