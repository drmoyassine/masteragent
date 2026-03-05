# MasterAgent — Prompt Manager & Agent Memory System

<div align="center">

![MasterAgent](https://img.shields.io/badge/MasterAgent-AI%20Agent%20Infrastructure-22C55E?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

**Complete infrastructure for AI agents: version-controlled prompts + persistent memory**

[Getting Started](#getting-started) • [Features](#features) • [API Reference](#api-reference) • [Deployment](#deployment)

</div>

---

## Overview

MasterAgent provides two essential modules for building production-ready AI agents:

1. **Prompt Manager** — Version-controlled prompts stored in GitHub, consumable via HTTP API
2. **Memory System** — Persistent 4-tier memory with pgvector semantic search, entity tracking, and lesson extraction

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.11+) |
| Frontend | React 18, Tailwind CSS, Shadcn/UI |
| Database | PostgreSQL 16 + pgvector (single unified instance) |
| Cache | Redis 7 |
| NER Engine | GLiNER (optional, Docker profile) |
| Authentication | JWT (admin), API Keys (agents) |
| Containerization | Docker, Docker Compose |

## Features

### Prompt Manager
- **Multi-file Markdown Structure** — Organize complex prompts as ordered sections
- **Git-backed Versioning** — Every version maps to a GitHub branch
- **Variable Injection** — Mustache-style placeholders with runtime injection
- **Render API** — Clean HTTP endpoints for consuming compiled prompts
- **Starter Templates** — Agent Persona, Task Executor, Knowledge Expert, and more
- **API Key Authentication** — Secure access for your agents

### Memory System
- **4-Tier Memory Architecture** — Interactions → Memories (T1) → Insights (T2) → Lessons (T3)
- **Semantic Search** — pgvector-powered similarity search across all memory tiers
- **Entity Timelines** — Track interaction history for contacts, organizations, projects
- **Curated Lessons** — Extract and organize knowledge from interactions
- **GLiNER NER** — Optional entity extraction (falls back to LLM)
- **PII Scrubbing** — Configurable PII protection for shared memories
- **Admin-configurable LLMs** — Separate APIs for summarization, embedding, vision, NER, PII
- **Webhook Ingestion** — Ingest interactions from external systems via signed webhooks
- **System Monitor** — Live stats dashboard with agent activity

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ (local frontend development only)
- Python 3.11+ (local backend development only)
- GitHub account (optional, for Prompt Manager cloud storage)

### Quick Start with Docker

```bash
git clone https://github.com/drmoyassine/masteragent.git
cd masteragent

cp .env.example .env
# Edit .env: set JWT_SECRET_KEY, ADMIN_PASSWORD, and optionally LLM API keys

docker compose up -d

# App is available at http://localhost:8080 (or your configured PORT)
```

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/memory
export MEMORY_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/memory
export REDIS_URL=redis://localhost:6379
python -m uvicorn server:app --reload --port 8084

# Frontend
cd frontend
yarn install
yarn start   # http://localhost:3000

# GLiNER Service (optional)
docker compose --profile gliner up gliner
```

### Environment Variables

See [`.env.example`](.env.example) for the full reference. Key variables:

```bash
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/memory
MEMORY_POSTGRES_URL=postgresql://postgres:postgres@postgres:5432/memory
REDIS_URL=redis://redis:6379/0
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change_me_in_production
```

## Project Structure

```
masteragent/
├── backend/
│   ├── core/                  # Shared DB and Auth utilities
│   │   ├── db.py              # PostgreSQL connection, DATABASE_URL resolution
│   │   ├── auth.py            # JWT + API key authentication
│   │   └── storage.py         # Memory DB context manager
│   ├── routes/                # Prompt Manager endpoints (auth, prompts, render, etc.)
│   ├── memory/                # Memory System
│   │   ├── __init__.py        # Router assembly (prefix: /api/memory)
│   │   ├── admin.py           # Admin CRUD: insights, lessons, stats
│   │   ├── agent.py           # Agent APIs: ingest, search, timeline
│   │   ├── config.py          # Config endpoints: entity types, LLM configs, agents
│   │   ├── auth.py            # Memory auth helpers
│   │   ├── webhooks.py        # Webhook source management + inbound routing
│   │   └── workspace.py       # Per-entity workspace chat
│   ├── services/              # Shared service layer (top-level, no circular deps)
│   │   ├── config_helpers.py  # DB-backed config lookups
│   │   ├── llm.py             # LLM call abstraction
│   │   ├── embeddings.py      # Embedding generation
│   │   ├── search.py          # pgvector semantic search
│   │   └── processing.py      # Text processing, PII, NER, chunking
│   ├── memory_db.py           # Memory schema initialization + migrations
│   ├── memory_models.py       # Pydantic models
│   ├── memory_services.py     # Backward-compat shim → services/
│   ├── memory_tasks.py        # Background tasks (OpenClaw sync, lesson mining)
│   ├── db_init.py             # Prompt manager schema initialization
│   ├── server.py              # FastAPI entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/             # PromptEditorPage, MemoryExplorerPage, SystemMonitor, etc.
│   │   ├── components/        # Shared UI components (Shadcn/UI)
│   │   └── lib/api.js         # API client
│   └── package.json
├── gliner/                    # Optional GLiNER NER microservice
│   ├── app.py
│   └── Dockerfile
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

## API Reference

### Authentication

Admin JWT:
```bash
curl -X POST /api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "yourpassword"}'
```

Agent API Key (returned when creating an agent):
```bash
curl -H "X-API-Key: mem_xxxx" /api/memory/interactions
```

### Prompt Manager Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prompts` | List all prompts |
| POST | `/api/prompts` | Create prompt |
| GET | `/api/prompts/{id}` | Get prompt |
| PUT | `/api/prompts/{id}` | Update prompt |
| DELETE | `/api/prompts/{id}` | Delete prompt |
| POST | `/api/prompts/{id}/{version}/render` | Render compiled prompt |
| GET | `/api/templates` | List starter templates |

### Memory System Endpoints

#### Config (JWT Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST/DELETE | `/api/memory/config/entity-types` | Entity type management |
| GET/POST/DELETE | `/api/memory/config/lesson-types` | Lesson type management |
| GET/POST/DELETE | `/api/memory/config/channel-types` | Channel type management |
| GET/POST/PATCH | `/api/memory/config/agents` | Agent management |
| GET/PUT | `/api/memory/config/llm-configs/{task_type}` | LLM configuration |
| GET/PUT | `/api/memory/config/settings` | Global memory settings |
| GET/POST | `/api/memory/config/system-prompts` | System prompts |

#### Agent APIs (API Key Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/memory/interactions` | Ingest interaction |
| POST | `/api/memory/search` | Semantic search |
| GET | `/api/memory/timeline/{type}/{id}` | Entity timeline |
| GET | `/api/memory/lessons` | List lessons |

#### Admin APIs (JWT Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/admin/stats` | System-wide counts |
| GET | `/api/memory/admin/stats/agents` | Per-agent activity |
| GET/POST/PATCH/DELETE | `/api/memory/insights` | Insight CRUD |
| GET/POST/PATCH/DELETE | `/api/memory/lessons` | Lesson CRUD |
| GET | `/api/memory/interactions` | Interaction log |
| GET | `/api/memory/audit-log` | Audit log |
| POST | `/api/memory/trigger/compact/{type}/{id}` | Trigger compaction |
| POST | `/api/memory/trigger/generate-memories` | Trigger memory generation |

#### Webhooks (JWT Auth for management, HMAC-signed for inbound)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/memory/webhooks/sources` | Webhook source management |
| POST | `/api/memory/webhooks/inbound/{source_id}` | Receive signed webhook payload |

### Example: Ingest an Interaction

```python
import requests

response = requests.post(
    "https://your-domain.com/api/memory/interactions",
    headers={"X-API-Key": "mem_xxxx"},
    data={
        "text": "Meeting with John from Acme about the partnership deal.",
        "channel": "meeting",
        "entities": '[{"type": "contact", "name": "John", "role": "primary"}]',
    }
)
```

### Example: Semantic Search

```python
response = requests.post(
    "https://your-domain.com/api/memory/search",
    headers={"X-API-Key": "mem_xxxx"},
    json={"query": "Acme partnership discussions", "limit": 10}
)
```

## Deployment

### Docker Compose (EasyPanel / VPS)

All ports are managed internally — no host port conflicts between instances:

```bash
cp .env.example .env
# Configure secrets in .env
docker compose up -d
```

The `masteragent` service runs nginx + uvicorn via supervisord in one container. PostgreSQL and Redis are internal-only (no exposed host ports).

### Production Checklist

- [ ] Set a strong `JWT_SECRET_KEY` (`openssl rand -hex 32`)
- [ ] Change `ADMIN_PASSWORD` from default
- [ ] Configure LLM API keys in admin UI → Memory Settings → LLM APIs
- [ ] Enable HTTPS (via reverse proxy / EasyPanel)
- [ ] Set up regular PostgreSQL backups

## Default Admin Credentials

```
Email:    admin@masteragent.ai   (set ADMIN_EMAIL in .env)
Password: change_me_in_production (set ADMIN_PASSWORD in .env)
```

⚠️ **Change these immediately in production!**

## Testing

```bash
cd backend/tests
# Requires a running server (see local dev above)
export MEMORY_TEST_BASE_URL=http://localhost:8084
python -m pytest . -v --timeout=30
# Expected: 101 passed, 2 skipped
```

The 2 skipped tests require live LLM API keys (`test_interactions_with_valid_api_key`, `test_ingest_and_verify_storage`).

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
Built for AI Agent Developers
</div>
