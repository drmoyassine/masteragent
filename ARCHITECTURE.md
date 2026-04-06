# MasterAgent — Architecture Reference

> **Last Updated**: 2026-03-05
> **Purpose**: Living reference for technical design, system boundaries, and structural patterns.

---

## 1. High-Level Overview

MasterAgent provides two tightly coupled but domain-separated modules within a single FastAPI runtime:

1. **Prompt Manager** — Git-backed version control for structured AI prompts
2. **Memory System** — 4-tier persistent agent memory with pgvector semantic search

Both modules share a single **PostgreSQL 16 + pgvector** instance. Redis provides caching and queuing for the memory system.

---

## 2. Infrastructure & Routing

### Entry Point
`backend/server.py` — thin entry point responsible only for:
- Loading environment variables
- Mounting CORS middleware
- Registering `APIRouter` instances
- Calling `init_db()` and `init_memory_db()` on startup

### Router Layout

| Namespace | Module | Purpose |
|---|---|---|
| `/api/auth`, `/api/prompts`, `/api/render`, `/api/settings`, `/api/templates` | `backend/routes/` | Prompt Manager |
| `/api/memory/config/*` | `backend/memory/config.py` | Memory admin config |
| `/api/memory/admin/*`, `/api/memory/insights`, `/api/memory/lessons` | `backend/memory/admin.py` | Memory admin CRUD + stats |
| `/api/memory/interactions`, `/api/memory/search`, `/api/memory/timeline`, `/api/memory/lessons` | `backend/memory/agent.py` | Agent-facing APIs |
| `/api/memory/webhooks/*` | `backend/memory/webhooks.py` | Webhook sources + inbound routing |
| `/api/memory/workspace/*` | `backend/memory/workspace.py` | Per-entity workspace chat |

The `memory/` sub-package assembles all its routers in `memory/__init__.py` under the `APIRouter(prefix="/api/memory")`.

---

## 3. Service Layer

The `backend/services/` package contains all infrastructure-facing business logic, kept at the top level to avoid circular imports with the `memory/` sub-package:

| Module | Responsibility |
|---|---|
| `services/config_helpers.py` | DB-backed config lookups (LLM configs, memory settings, system prompts) |
| `services/llm.py` | OpenAI-compatible LLM call abstraction |
| `services/embeddings.py` | Embedding generation via configured APIs |
| `services/search.py` | pgvector semantic search across memory tiers |
| `services/processing.py` | Text chunking, PII scrubbing, summarization, NER, document parsing |

`memory_services.py` is a backward-compatibility shim that re-exports from `services/`.

---

## 4. Database Architecture

A single PostgreSQL instance hosts all tables. Schema is split by domain:

### Prompt Manager Tables (`db_init.py`)
- `users`, `api_keys`, `settings`, `prompts`, `prompt_sections`, `prompt_versions`, `templates`, `variables`, `account_variables`, `prompt_variables`

### Memory System Tables (`memory_db.py`)
- **Config**: `memory_entity_types`, `memory_entity_subtypes`, `memory_lesson_types`, `memory_channel_types`, `memory_agents`, `memory_llm_configs`, `memory_system_prompts`, `memory_settings`, `memory_entity_type_config`
- **Data**: `interactions`, `memories`, `memory_documents`, `insights`, `lessons`, `memory_audit_log`, `webhook_sources`

All memory tables have an `embedding vector(1536)` column (or equivalent) enabled by the `pgvector` extension for semantic search.

### Context Managers
- `core.db.get_db_context()` → Prompt Manager DB
- `core.storage.get_memory_db_context()` → Memory DB (both point to the same PostgreSQL instance via `MEMORY_POSTGRES_URL`)

---

## 5. 4-Tier Memory Model

```
Tier 0: Interactions (raw events — POST /api/memory/interactions)
    ↓  (batch processing / compaction)
Tier 1: Memories (chunked, embedded, searchable)
    ↓  (threshold-based compaction)
Tier 2: Insights (patterns + trends, draft → confirmed)
    ↓  (admin promotion)
Tier 3: Lessons (organization-wide knowledge)
```

---

## 6. Authentication Matrix

| Consumer | Mechanism | Header | Handler |
|---|---|---|---|
| Human admins | JWT (Bearer) | `Authorization: Bearer <token>` | `memory.auth.require_admin_auth()` |
| AI agents / scripts | API Key | `X-API-Key: <key>` | `core.auth.verify_agent_key()` |
| Webhook sources | HMAC-SHA256 signature | `X-Webhook-Signature: <sig>` | `memory.webhooks` inline validation |

Agent API Keys are SHA-256 hashed before storage. The plaintext key is returned only once at creation time.

---

## 7. Storage Subsystem (Prompt Manager)

The Prompt Manager uses a pluggable storage factory (`storage_service.py`):

- **`GitHubStorageService`** — Active when `github_token` is configured. Commits directly to the user's configured repo/branch.
- **`LocalStorageService`** — Fallback when GitHub is not configured. Persists to `backend/local_prompts/{user_id}/`.

---

## 8. Deployment Topology

```
VPS / EasyPanel
├── masteragent container (supervisord)
│   ├── nginx :80          → serves React build, proxies /api/ → uvicorn
│   └── uvicorn :8001      → FastAPI application
├── postgres container (pgvector/pgvector:pg16)
│   └── :5432 (internal only — not exposed to host)
└── redis container (redis:7-alpine)
    └── :6379 (internal only — not exposed to host)
```

All inter-container communication is via Docker Compose service names (`postgres`, `redis`). Only the `masteragent` service's HTTP port is managed externally (by EasyPanel's override file).

GLiNER is optional, started with `docker compose --profile gliner up`.

---

## 9. DATABASE_URL Resolution Order

`core/db.py` resolves the PostgreSQL connection URL as follows:

1. `DATABASE_URL` env var (if set and not a SQLite URI)
2. `MEMORY_POSTGRES_URL` env var
3. Hard-coded default: `postgresql://postgres:postgres@postgres:5432/memory`

This ensures the backend connects correctly inside Docker even without explicit configuration.

---

## 10. Frontend Conventions

- **Framework**: React 18 SPA, bootstrapped with Create React App + CRACO
- **State**: `ConfigContext.jsx` manages storage mode (`github` vs `local`)
- **Path Alias**: `@/` maps to `frontend/src/`
- **API Layer**: All calls centralized in `frontend/src/lib/api.js`
- **UI Components**: Shadcn/UI component library

*Update this document when significant infrastructure changes are made.*
