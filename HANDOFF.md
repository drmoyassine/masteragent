# MasterAgent — Handoff Document

> **Last Updated**: 2026-03-05
> **Status**: Production-deployed MVP — PostgreSQL-only stack, 101/103 tests passing
> **Priority**: Configure LLM API keys in admin UI to enable summarization and semantic search

---

## ✅ Current State Summary

The platform is deployed and operational. All core functionality is implemented:

### Infrastructure (Complete)
- **Single-DB Architecture**: PostgreSQL 16 + pgvector for both Prompt Manager and Memory System (Qdrant removed)
- **Redis**: Operational for caching/queuing
- **Docker Compose**: Multi-service stack with correct internal networking (no host port conflicts)
- **EasyPanel deployment**: Tested and working with multiple concurrent instances

### Backend (Complete)
- **Prompt Manager**: Full CRUD, GitHub storage, local fallback, variable injection, template system
- **Memory System**: 4-tier memory (Interactions → Memories → Insights → Lessons)
  - Ingestion pipeline with chunking, NER, summarization, embedding
  - pgvector semantic search
  - Entity timelines
  - Webhook source management + HMAC-signed inbound routing
  - Per-entity workspace chat
  - Admin stats: `GET /api/memory/admin/stats` and `/api/memory/admin/stats/agents`
- **Authentication**: JWT (admin), API Keys (agents), HMAC (webhooks)
- **Refactoring complete**: `services/` top-level package extracted to resolve circular imports

### Tests (101/103 passing)
- 2 skipped tests require live LLM API keys
- Test suite covers auth, config, admin CRUD, interactions, search, webhooks, workspace chat

---

## 🔴 Next Steps

### P0 — Required for full functionality
1. **Configure LLM API keys** in admin UI → Memory Settings → LLM APIs
   - Add keys for: `summarization`, `embedding`, `vision`, `entity_extraction`, `pii_scrubbing`
   - Without embedding config, semantic search returns 503

2. **Implement background task scheduler**
   - `memory_tasks.py` has OpenClaw sync and lesson mining stubs
   - Currently triggered manually via System Monitor UI buttons
   - Add `asyncio` periodic task or APScheduler on server startup

### P1 — Important features
3. **Bulk import/export** — JSON/CSV memory import, ZIP export
4. **Real-time System Monitor** — WebSocket-based live activity stream
5. **GLiNER model customization** — Custom entity labels per deployment
6. **Deeper LLM tuning** — Model parameter configuration per task type

---

## File Reference

### Backend

```
backend/
├── server.py              # FastAPI entry point — thin, mounts all routers
├── db_init.py             # Prompt Manager schema (PostgreSQL)
├── memory_db.py           # Memory System schema and idempotent migrations
├── memory_models.py       # All Pydantic request/response models
├── memory_services.py     # Backward-compat shim → services/
├── memory_tasks.py        # Background: OpenClaw sync, lesson mining
├── core/
│   ├── db.py              # DATABASE_URL resolution, get_db_context()
│   ├── auth.py            # JWT, API key, password hashing
│   └── storage.py         # Memory DB context (get_memory_db_context())
├── routes/                # Prompt Manager: auth, prompts, render, settings, templates
├── memory/
│   ├── __init__.py        # Assembles all memory routers under /api/memory
│   ├── admin.py           # Admin CRUD: insights, lessons, stats, triggers, audit log
│   ├── agent.py           # Agent APIs: ingest, search, timeline, lessons
│   ├── config.py          # Config: entity types, agents, LLM configs, settings
│   ├── auth.py            # require_admin_auth() for memory system
│   ├── webhooks.py        # Webhook source management + HMAC-signed inbound
│   └── workspace.py       # Per-entity workspace chat endpoint
└── services/
    ├── config_helpers.py  # DB-backed: get_memory_settings(), get_llm_config()
    ├── llm.py             # call_llm() — OpenAI-compatible
    ├── embeddings.py      # get_embedding()
    ├── search.py          # pgvector_search()
    └── processing.py      # chunk_text(), scrub_pii(), summarize(), extract_entities()
```

### Frontend

```
frontend/src/
├── pages/
│   ├── DashboardPage.jsx          # Prompt list
│   ├── PromptEditorPage.jsx       # Prompt editor with DnD sections
│   ├── MemorySettingsPage.jsx     # Memory admin config (6 tabs)
│   ├── MemoryExplorerPage.jsx     # Search, timeline, lessons
│   └── MemoryMonitorPage.jsx      # System Monitor: stats, task triggers
├── components/
│   ├── layout/MainLayout.jsx      # Navigation (7 items)
│   ├── VariableAutocomplete.jsx   # @ trigger popover
│   └── ui/                        # Shadcn/UI components
└── lib/api.js                     # All API functions
```

### Docker

```
docker-compose.yml      # masteragent + postgres + redis (+ gliner profile)
Dockerfile              # Multi-stage: React build → nginx + Python + supervisord
.env.example            # Full environment variable reference
```

---

## API Endpoints Summary

### Health
```
GET  /api/health
GET  /api/memory/health
```

### Auth
```
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

### Prompt Manager (JWT Required)
```
GET/POST                    /api/prompts
GET/PUT/DELETE              /api/prompts/{id}
GET/POST                    /api/prompts/{id}/sections
PATCH                       /api/prompts/{id}/sections/reorder
POST                        /api/prompts/{id}/{version}/render
GET                         /api/templates
GET/PUT                     /api/settings
GET/POST/DELETE             /api/variables/account
GET/POST/DELETE             /api/variables/prompt/{prompt_id}
```

### Memory Config (JWT Required)
```
GET/POST/DELETE             /api/memory/config/entity-types
GET/POST/DELETE             /api/memory/config/entity-subtypes
GET/POST/DELETE             /api/memory/config/lesson-types
GET/POST/DELETE             /api/memory/config/channel-types
GET/POST/PATCH/DELETE       /api/memory/config/agents
GET/PUT                     /api/memory/config/llm-configs/{task_type}
GET/POST/PUT/DELETE         /api/memory/config/system-prompts
GET/PUT                     /api/memory/config/settings
```

### Agent APIs (API Key Required)
```
POST  /api/memory/interactions
POST  /api/memory/search
GET   /api/memory/timeline/{type}/{id}
GET   /api/memory/lessons
```

### Admin APIs (JWT Required)
```
GET                         /api/memory/admin/stats
GET                         /api/memory/admin/stats/agents
GET/POST/PATCH/DELETE       /api/memory/insights
GET/POST/PATCH/DELETE       /api/memory/lessons
GET                         /api/memory/interactions
GET                         /api/memory/interactions/{id}
GET                         /api/memory/audit-log
GET/PATCH                   /api/memory/entity-type-config/{entity_type}
POST                        /api/memory/trigger/compact/{entity_type}/{entity_id}
POST                        /api/memory/trigger/generate-memories
```

### Webhooks
```
GET/POST                    /api/memory/webhooks/sources        (JWT required)
PATCH/DELETE                /api/memory/webhooks/sources/{id}   (JWT required)
POST                        /api/memory/webhooks/sources/{id}/rotate  (JWT required)
POST                        /api/memory/webhooks/inbound/{source_id}  (HMAC signed)
```

### Workspace Chat
```
POST  /api/memory/workspace/{entity_type}/{entity_id}/chat          (API Key)
POST  /api/memory/workspace/{entity_type}/{entity_id}/chat/admin    (JWT)
```

---

## Quick Commands

```powershell
# Local server
cd backend
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/memory"
$env:MEMORY_POSTGRES_URL="postgresql://postgres:postgres@localhost:5432/memory"
$env:REDIS_URL="redis://localhost:6379"
python -m uvicorn server:app --port 8084

# Run tests
cd backend\tests
$env:MEMORY_TEST_BASE_URL="http://localhost:8084"
python -m pytest . -v --timeout=30

# Docker
docker compose up -d            # Start all services
docker compose logs -f          # Follow logs
docker compose down             # Stop all
docker compose build --no-cache # Force fresh image build
```

---

Good luck! 🚀
