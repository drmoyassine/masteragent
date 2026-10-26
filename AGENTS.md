# AGENTS.md

This file provides guidance to AI agents working with this repository.

## Project Overview

**MasterAgent** — Full-stack AI agent infrastructure providing:
1. **Prompt Manager** — Git-backed version-controlled AI prompts, consumed via API or MCP
2. **Memory System** — 4-tier persistent memory (Interactions → Memories → Intelligence → Knowledge) with pgvector semantic search

Single-tenant in code (one users table, one admin, no tenant column); isolation comes from one deployment per tenant. Per-agent entity scoping (`ENFORCE_AGENT_SCOPE`) is agent-key authorization, not tenancy.

## Architecture Quick Reference

### Single PostgreSQL Database
Both modules share one PostgreSQL 16 + pgvector instance:
- Use `core.db.get_db_context()` for Prompt Manager tables
- Use `core.storage.get_memory_db_context()` for Memory System tables
- Connection resolved via: `DATABASE_URL` → `MEMORY_POSTGRES_URL` → default `postgres:5432`
- Schema: Prompt Manager tables from `db_init.py`; memory tables from `memory_system/store/db.py`; forward-only SQL migrations in `backend/migrations/` (`001_baseline` … `006_vision_webhook_secret`), applied by the runner in `memory_system/store/migrations.py`

### Authentication
- **JWT (Bearer token)**: Admin/config endpoints — `memory.auth.require_admin_auth()`, `core.auth.require_admin_auth()`. JWTs carry a `tver` claim matched against `users.token_version` (TASK-259 revocation)
- **API Key (X-API-Key header)**: Agent-facing endpoints — `core.auth.verify_agent_key()`; SHA-256 hashed at rest, scoped by `memory_agent_entities` grants
- **HMAC-SHA256**: Webhook inbound validation (inline in `memory/webhooks.py`)
- **MCP Service Key**: `MCP_SERVICE_KEY` authenticates only as the non-admin `mcp-service` identity

### Service Ports (Local Dev)
- Backend: `8084` (local), `8001` (Docker internal)
- PostgreSQL: `5432`
- Redis: `6379`
- GLiNER NER: `8002` (optional Docker profile)
- Health: `GET /api/health` — checks Postgres, Redis, scheduler-tick freshness, BullMQ job state

### Key Packages
```
backend/
├── core/               # Shared DB, auth, storage utilities
├── routes/             # Prompt Manager endpoints
├── memory/             # Memory System HTTP layer
│   │                   #   routers: agent, admin, config, webhooks, workspace, access, auth
│   └── queue.py        # BullMQ worker (python bullmq pkg) — declarative JobSpec
│                       #   registry, typed payloads, bounded job retention
├── memory_system/      # Memory pipeline package (TASK-257):
│   ├── store/          # db.py (schema), models, writes, helpers, migrations
│   ├── ingest/         # interaction ingestion + rate limiting
│   ├── distill/        # generation, knowledge, playbooks, telemetry, prior_context
│   ├── maintain/       # clustering, consolidation, erasure, embedding backfill,
│   │                   #   interaction retention, quality
│   └── scheduler.py    # 60s background loop; per-day job claims (memory_job_log)
├── services/           # Infrastructure services (top-level to avoid circular
│                       #   imports with memory/): llm, embeddings, search, processing,
│                       #   prompt_safety (untrusted-content doctrine), budget,
│                       #   alert_delivery, job_safety, parse_runner, vision_webhooks,
│                       #   outbound_webhooks, memory_lock, provider_batch
├── migrations/         # Forward-only SQL migrations (001–006)
├── server.py           # FastAPI entry point
├── db_init.py          # Prompt Manager schema
└── storage_service.py  # Prompt storage factory
```

### MCP
Two fastapi-mcp servers, Streamable HTTP: `/api/prompts/mcp` and `/api/memory/mcp`.
The server executes tools by calling back into itself (`MCP_BASE_URL`, default `http://127.0.0.1:8001`); `mcp_utils.sanitize_tools_for_gemini` strips schema constructs Gemini rejects.

## Build & Run Commands

```bash
# Backend (local)
cd backend
pip install -r requirements.txt
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/memory"
$env:MEMORY_POSTGRES_URL="postgresql://postgres:postgres@localhost:5432/memory"
$env:REDIS_URL="redis://localhost:6379"
python -m uvicorn server:app --port 8084

# Optional: delegate document parsing + audio transcription to the liteparse runner
$env:PARSE_RUNNER_URL="http://localhost:PORT"
$env:PARSE_RUNNER_API_KEY="..."

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
# Hermetic suite (default): requires Docker on the machine; boots the REAL app
# in-process against throwaway Postgres(pgvector)+Redis testcontainers
cd backend
python -m pytest

# Live stack instead: point at a running deployment
$env:MEMORY_TEST_BASE_URL="http://localhost:8084"
# optional: MEMORY_TEST_EMAIL / MEMORY_TEST_PASSWORD / MEMORY_TEST_AGENT_KEY

# End-to-end pipeline tests (need a configured LLM provider + running workers;
# excluded from the default gate)
python -m pytest -m live_pipeline
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
LLM configs are keyed by `task_type` (e.g. `summarization`, `embedding`, `vision`, `entity_extraction`, `pii_scrubbing`; pipeline nodes define more). Looked up via `services.config_helpers.get_llm_config()`.

### Production Compatibility Controls
Legacy-compat escape hatches — deliberate defaults, decide each explicitly before changing:
- `ENFORCE_AGENT_SCOPE=false` — preserves historical cross-agent entity access
- `REQUIRE_WEBHOOK_TIMESTAMP=false` — preserves webhook senders without replay headers
- `ALLOW_PUBLIC_SIGNUP=true` — preserves signup; registered users are not administrators
- `STRICT_STARTUP_VALIDATION=false` — warns rather than aborting on legacy secrets

Rollout guide archived at `docs/plans/archived/production-hardening-rollout.md`.

### AI Safety (Untrusted-Content Doctrine)
Every interaction enters from outside, so distilled output is externally-derived by construction. `services/prompt_safety.py` frames untrusted content (`frame_untrusted`), scans outputs for injection-shaped directives (flag-only), and forces draft status on externally-derived skills/playbooks (`resolve_creation_status`). Entity erasure lives in `memory_system/maintain/erasure.py`. See ARCHITECTURE.md §11.

### Frontend Conventions
- Framework: React 19 SPA (CRA + CRACO), Shadcn/UI
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
- `promptsrc_data` → `/app/backend/data`
- `promptsrc_prompts` → `/app/backend/local_prompts/`
- `promptsrc_db` → `/app/backend/db/`
- `postgres_data` → PostgreSQL data directory
- `redis_data` → Redis AOF persistence

`db_backup` service produces atomic dumps (writes `.part`, renames on success).

### Admin Credentials (Default)
```
Email:    set via ADMIN_EMAIL env var
Password: set via ADMIN_PASSWORD env var
Default:  admin@masteragent.ai / change_me_in_production
```

## Related Documentation
- `ARCHITECTURE.md` — Full system architecture (incl. tenancy posture §6, AI safety §11)
- `memory/PRD.md` — Memory system product requirements
- `.env.example` — Full environment variable reference
