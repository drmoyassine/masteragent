# MasterAgent — Prompt Manager & Agent Memory System

<div align="center">

![MasterAgent](https://img.shields.io/badge/MasterAgent-AI%20Agent%20Infrastructure-22C55E?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-Streamable%20HTTP-blue?style=flat-square)

**Complete infrastructure for AI agents: version-controlled prompts + persistent memory + MCP integration**

[Getting Started](#getting-started) • [Features](#features) • [API Reference](#api-reference) • [MCP Integration](#mcp-integration) • [Deployment](#deployment)

</div>

---

## Overview

MasterAgent provides two essential modules for building production-ready AI agents:

1. **Prompt Manager** — Version-controlled prompts stored in GitHub, consumable via HTTP API or MCP
2. **Memory System** — Persistent 4-tier memory with pgvector semantic search, entity tracking, and intelligence extraction

Both are exposed as **MCP tools** via streamable HTTP — connect any MCP-compatible agent (n8n, Claude, etc.) with a single URL instead of wiring individual HTTP requests.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.11+) |
| Frontend | React 19, Tailwind CSS, Shadcn/UI |
| Database | PostgreSQL 16 + pgvector |
| Queue | Redis 7 + BullMQ |
| MCP | fastapi-mcp (Streamable HTTP) |
| NER Engine | GLiNER (optional, Docker profile) |
| Authentication | JWT (admin), API Keys (agents), MCP Service Key |

## Features

### Prompt Manager
- **Multi-file Markdown Structure** — Organize complex prompts as ordered sections
- **Git-backed Versioning** — Every version maps to a GitHub branch
- **Variable Injection** — Mustache-style placeholders with account-level and prompt-level scoping
- **Render API** — Clean HTTP endpoints for consuming compiled prompts
- **Starter Templates** — Agent Persona, Task Executor, Knowledge Expert, and more
- **API Key Authentication** — Secure access for your agents
- **Role-separated Administration** — Prompt users cannot administer memory infrastructure

### Memory System
- **4-Tier Memory Architecture** — Interactions → Memories (T1) → Intelligence (T2) → Knowledge (T3)
- **Automated Pipeline** — Background tasks for memory generation, intelligence extraction, and knowledge promotion
- **Semantic Search** — pgvector-powered similarity search across all memory tiers
- **Fulltext Search** — PostgreSQL full-text search with ranking
- **Entity Timelines** — Track interaction history for contacts, organizations, projects
- **Entity Profiles** — Auto-extracted and syncable entity data with NER
- **Curated Knowledge** — Extract, approve, and organize knowledge from intelligence
- **GLiNER NER** — Optional entity extraction (falls back to LLM)
- **PII Scrubbing** — Configurable PII protection for shared memories
- **Admin-configurable LLMs** — Separate APIs for summarization, embedding, vision, NER, PII
- **Outbound Webhooks** — Fire webhooks on memory/intelligence/knowledge events
- **Webhook Ingestion** — Ingest interactions from external systems via HMAC-signed webhooks
- **System Monitor** — Live stats dashboard with agent activity and audit log
- **Workspace Chat** — Per-entity conversational context retrieval

### MCP Integration
- **Two MCP Servers** — Separate endpoints for prompts and memory, each auto-discovering available tools
- **Streamable HTTP** — Modern MCP transport (no SSE dependency)
- **Service Key Auth** — Single `MCP_SERVICE_KEY` env var authenticates all tool calls
- **Optional Agent Entity Isolation** — Gradual production rollout through `ENFORCE_AGENT_SCOPE`
- **n8n Ready** — Add an MCP Client node, point to the URL, tools auto-populate

### Multimodal Data Ingestion
- **Native PDF OCR** — Scanned documents via PyMuPDF with visually optimized frames for Vision LLMs
- **Smart Spreadsheets (`.xlsx`)** — Token-efficient Markdown table serialization
- **XML Documents (`.docx`)** — Dependency-free text extraction from `.docx` XML trees
- **Image Processing** — Content extraction and indexing (`.jpg`, `.png`, `.webp`)
- **Graceful Formatting** — Fallback protocol for legacy binaries (`.doc`, `.xls`)

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

# App is available at http://localhost:8080
```

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/memory
export MEMORY_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/memory
export REDIS_URL=redis://localhost:6379
export MCP_SERVICE_KEY=your-secret-key
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
MCP_SERVICE_KEY=<generate with: openssl rand -hex 32>
DATA_ENCRYPTION_KEY=<generate independently with: openssl rand -hex 32>
```

## Project Structure

```
masteragent/
├── backend/
│   ├── core/                  # Shared DB and Auth utilities
│   │   ├── auth.py            # JWT + API key + MCP service key auth
│   │   ├── db.py              # PostgreSQL connection, DATABASE_URL resolution
│   │   ├── storage.py         # Memory DB context manager
│   │   └── utils.py           # Shared utilities
│   ├── routes/                # Prompt Manager endpoints
│   │   ├── auth.py            # Login, signup, GitHub OAuth
│   │   ├── prompts.py         # Prompt CRUD, sections, versions
│   │   ├── render.py          # Prompt rendering
│   │   ├── templates.py       # Starter templates
│   │   ├── variables.py       # Account + prompt variables
│   │   ├── settings.py        # App settings
│   │   └── api_keys.py        # API key management
│   ├── memory/                # Memory System
│   │   ├── __init__.py        # Router assembly (prefix: /api/memory)
│   │   ├── agent.py           # Agent SDK: ingest, search, CRUD
│   │   ├── admin.py           # Admin CRUD: stats, bulk ops, triggers
│   │   ├── config.py          # Entity types, agents, LLM configs
│   │   ├── auth.py            # Agent key + MCP service key auth
│   │   ├── webhooks.py        # Webhook source management + inbound routing
│   │   ├── workspace.py       # Per-entity workspace chat
│   │   ├── queue.py           # BullMQ worker management
│   │   └── services/          # Memory-specific services
│   │       ├── llm.py         # LLM call abstraction
│   │       ├── embeddings.py  # Embedding generation
│   │       ├── search.py      # pgvector semantic search
│   │       ├── processing.py  # Text processing, PII, NER, chunking
│   │       └── config_helpers.py
│   ├── services/              # Shared service layer
│   │   ├── llm.py             # LLM call abstraction
│   │   ├── embeddings.py      # Embedding generation
│   │   ├── search.py          # pgvector semantic search
│   │   ├── processing.py      # Text processing, PII, NER, chunking
│   │   ├── config_helpers.py  # DB-backed config lookups
│   │   ├── prompt_renderer.py # Mustache variable injection
│   │   └── outbound_webhooks.py
│   ├── memory_tasks.py        # Background task loop (thin shell)
│   ├── memory_ingestion.py    # Interaction ingestion pipeline
│   ├── memory_generation.py   # Daily memory generation pipeline
│   ├── memory_compaction.py   # Intelligence extraction pipeline
│   ├── memory_knowledge.py    # Knowledge promotion pipeline
│   ├── memory_db_writes.py    # DB insert helpers (memory, intelligence, knowledge)
│   ├── memory_prior_context.py # Prior-context fetchers
│   ├── memory_helpers.py      # Shared NER/formatting helpers
│   ├── memory_rate_limit.py   # Rate limiting
│   ├── memory_db.py           # Memory schema initialization + migrations
│   ├── memory_models.py       # Pydantic models
│   ├── db_init.py             # Prompt manager schema initialization
│   ├── server.py              # FastAPI entry point + MCP servers
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/             # PromptEditor, MemoryExplorer, SystemMonitor, etc.
│   │   ├── components/        # Shared UI components (Shadcn/UI)
│   │   ├── hooks/             # useBulkSelection, useColumnConfig, use-toast
│   │   └── lib/api.js         # API client
│   └── package.json
├── gliner/                    # Optional GLiNER NER microservice
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
| GET | `/api/prompts/{id}/sections` | List sections |
| POST | `/api/prompts/{id}/sections` | Create section |
| PUT | `/api/prompts/{id}/sections/{filename}` | Update section |
| DELETE | `/api/prompts/{id}/sections/{filename}` | Delete section |
| POST | `/api/prompts/{id}/sections/reorder` | Reorder sections |
| GET | `/api/prompts/{id}/versions` | List versions |
| POST | `/api/prompts/{id}/versions` | Create version |
| POST | `/api/prompts/{id}/{version}/render` | Render compiled prompt |
| GET | `/api/prompts/{id}/variables` | List prompt variables |
| POST | `/api/prompts/{id}/variables` | Create prompt variable |
| GET | `/api/account-variables` | List account variables |
| POST | `/api/account-variables` | Create account variable |
| GET | `/api/templates` | List starter templates |

### Memory Agent Endpoints (API Key Auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/memory/interactions` | Ingest interaction |
| GET | `/api/memory/interactions` | List interactions |
| PATCH | `/api/memory/interactions/{id}` | Update interaction |
| DELETE | `/api/memory/interactions/{id}` | Delete interaction |
| GET | `/api/memory/has-context` | Check if entity has memory |
| POST | `/api/memory/memories` | Create memory |
| GET | `/api/memory/memories` | List memories |
| PATCH | `/api/memory/memories/{id}` | Update memory |
| DELETE | `/api/memory/memories/{id}` | Delete memory |
| POST | `/api/memory/intelligence` | Create intelligence |
| GET | `/api/memory/intelligence` | List intelligence |
| PATCH | `/api/memory/intelligence/{id}` | Update intelligence |
| DELETE | `/api/memory/intelligence/{id}` | Delete intelligence |
| POST | `/api/memory/knowledge` | Create knowledge |
| GET | `/api/memory/knowledge` | List knowledge |
| PATCH | `/api/memory/knowledge/{id}` | Update knowledge |
| DELETE | `/api/memory/knowledge/{id}` | Delete knowledge |
| POST | `/api/memory/search/semantic` | Semantic vector search |
| POST | `/api/memory/search/fulltext` | Fulltext search |

### Admin Endpoints (JWT Auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/admin/stats` | System-wide counts |
| GET | `/api/memory/admin/stats/agents` | Per-agent activity |
| GET | `/api/memory/interactions` | Interaction log |
| GET | `/api/memory/admin/memories` | Memory management |
| GET | `/api/memory/intelligence` | Intelligence management |
| GET | `/api/memory/knowledge` | Knowledge management |
| GET | `/api/memory/audit-log` | Audit log |
| POST | `/api/memory/trigger/generate-memories` | Trigger memory generation |
| POST | `/api/memory/trigger/run-intelligence-check` | Trigger intelligence extraction |
| POST | `/api/memory/trigger/run-knowledge-check` | Trigger knowledge promotion |
| POST | `/api/memory/trigger/compact/{type}/{id}` | Trigger compaction |
| POST | `/api/memory/trigger/backfill-profiles` | Backfill entity profiles |
| GET/POST/PATCH/DELETE | `/api/memory/outbound-webhooks` | Outbound webhook management |
| GET/PATCH/DELETE | `/api/memory/webhooks` | Inbound webhook source management |

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
    "https://your-domain.com/api/memory/search/semantic",
    headers={"X-API-Key": "mem_xmmm"},
    json={"query": "Acme partnership discussions", "limit": 10}
)
```

## MCP Integration

MasterAgent exposes two MCP servers using the **Streamable HTTP** transport. Any MCP-compatible client (n8n, Claude Desktop, etc.) can connect and auto-discover available tools.

### Endpoints

| URL | Tools |
|-----|-------|
| `/api/prompts/mcp` | Prompt CRUD, sections, versions, render, variables |
| `/api/memory/mcp` | Ingest interactions, CRUD on memories/intelligence/knowledge, semantic + fulltext search |

### Connecting from n8n

1. Add an **MCP Client** node to your workflow
2. Set transport to **Streamable HTTP**
3. Set URL to `https://your-domain.com/api/memory/mcp` (or `/api/prompts/mcp`)
4. The AI agent auto-discovers and calls tools — no manual HTTP wiring needed

### Auth

Set `MCP_SERVICE_KEY` in your `.env`. The MCP server injects it into every tool call server-side — n8n doesn't need to pass credentials.

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
- [ ] Set a strong `MCP_SERVICE_KEY` (`openssl rand -hex 32`)
- [ ] Change `ADMIN_PASSWORD` from default
- [ ] Configure LLM API keys in admin UI → Memory Settings → LLM APIs
- [ ] Enable HTTPS (via reverse proxy / EasyPanel)
- [ ] Set up regular PostgreSQL backups

## Default Admin Credentials

```
Email:    admin@masteragent.ai   (set ADMIN_EMAIL in .env)
Password: change_me_in_production (set ADMIN_PASSWORD in .env)
```

> **Change these immediately in production!**

## Testing

```bash
cd backend/tests
export MEMORY_TEST_BASE_URL=http://localhost:8084
python -m pytest . -v --timeout=30
```

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
Built for AI Agent Developers
</div>
