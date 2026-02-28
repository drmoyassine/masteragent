# Project Overview

> **Last Updated**: 2026-02-27
> **Purpose**: Provides a high-level summary of the MasterAgent (PromptSRC) project for AI assistant context.

---

## Project Origin

The project began as a **Prompt Manager** - a standalone microservice to manage AI prompts as code. Prompts were stored as ordered Markdown files in a GitHub repository, versioned, and rendered via an API with variable injection.

The scope then expanded to include an **Agent-Facing Memory System** as an extension. This new system is **API-first**, designed to be a memory backend for AI agents where:
- Agents push data programmatically via API
- UI is used for configuration and read-only exploration only
- No data entry through the UI

**Key Architecture Principle**: The memory system maintains strict separation between private data and PII-scrubbed shared data across both the relational database and Qdrant collections.

---

## Project Identity

**Name**: MasterAgent (PromptSRC)  
**Tagline**: The complete infrastructure for AI agents: version-controlled prompts + persistent memory system  
**Status**: Production-Ready MVP

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| **Backend** | FastAPI (Python 3.11+) |
| **Frontend** | React 18/19, Tailwind CSS, Shadcn/UI |
| **Database (Dev)** | SQLite |
| **Database (Prod)** | PostgreSQL |
| **Vector Store** | Qdrant |
| **NER Engine** | GLiNER2 |
| **Authentication** | JWT (admin), API Keys (agents) |
| **Containerization** | Docker, Docker Compose |

---

## Architecture Overview

### Two Main Modules

1. **Prompt Manager**
   - Version-controlled prompts stored in GitHub
   - Multi-file Markdown structure with ordered sections
   - Variable injection (Mustache-style placeholders)
   - Render API with API key authentication
   - Starter templates for common agent patterns

2. **Memory System**
   - Persistent memory with semantic search
   - Entity tracking and timelines
   - Lesson extraction from interactions
   - PII scrubbing for shared memories
   - OpenClaw Markdown sync

### Dual Database System

| Database | Location | Purpose |
|----------|----------|---------|
| **Main DB** | `backend/prompt_manager.db` | Users, prompts, settings, API keys |
| **Memory DB** | `backend/data/memory.db` | Entity types, interactions, lessons, agents |

### Dual Authentication

| Type | Header | Use Case | Validator |
|------|--------|----------|-----------|
| **JWT** | `Authorization: Bearer <token>` | Admin/config endpoints | `require_admin_auth()` |
| **API Key** | `X-API-Key: <key>` | Agent-facing endpoints | `verify_agent_key()` |

---

## Service Ports

| Service | Docker Port | Local Dev Port |
|---------|-------------|----------------|
| Backend API | 8001 | 8000 |
| GLiNER NER | 8002 | 8002 |
| Qdrant REST | 6333 | 6333 |
| Qdrant gRPC | 6334 | 6334 |
| Frontend | 80 | 3000 |

---

## Key Directories

```
promptsrc/
├── backend/                    # FastAPI backend
│   ├── core/                  # DB connection and Auth singletons
│   ├── routes/                # Prompt Manager module endpoints
│   ├── memory/                # Memory System module endpoints
│   ├── server.py              # Root router mount
│   ├── memory_db.py           # Memory database schema
│   ├── memory_models.py       # Pydantic models
│   ├── memory_services.py     # LLM, embedding, Qdrant services
│   ├── memory_tasks.py        # Background tasks
│   ├── prompt_manager.db      # Main SQLite database
│   └── data/
│       └── memory.db          # Memory SQLite database
├── frontend/                   # React frontend
│   └── src/
│       ├── pages/             # Page components
│       ├── components/        # UI components (Shadcn)
│       ├── context/           # React context providers
│       ├── hooks/             # Custom hooks
│       └── lib/               # Utilities and API client
├── gliner/                     # GLiNER2 NER service
│   ├── app.py                 # FastAPI NER service
│   └── Dockerfile
├── memory/                     # Memory system documentation
│   └── PRD.md
├── test_reports/               # Test results and reports
├── .memory/                    # AI assistant memory bank
├── AGENTS.md                   # Agent guidance file
├── HANDOFF.md                  # Project handoff document
└── docker-compose.yml          # Docker orchestration
```

---

## Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@promptsrc.com` | `admin123` |

---

## Quick Commands

```bash
# Start all services (Docker)
docker-compose up --build

# Backend development
cd backend && pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# Frontend development
cd frontend && yarn install && yarn start

# Run tests
cd backend && pytest tests/ -v
```

---

## Related Files

- [`AGENTS.md`](../AGENTS.md) - Agent guidance for working with the codebase
- [`HANDOFF.md`](../HANDOFF.md) - Project handoff and current state
- [`README.md`](../README.md) - Full project documentation
