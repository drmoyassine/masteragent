# Prompt Manager & Memory System - Product Requirements Document

## Original Problem Statement
Build a **Prompt Manager** (prompt versioning as code using GitHub) extended with an **Agent-Facing Memory System** (API-first memory backend for AI agents).

---

## What's Implemented (February 2026)

### ✅ Complete

#### Prompt Manager
- Full-stack app with prompts, sections, versions
- Templates (Agent Persona, Task Executor, etc.)
- API keys for external access
- GitHub integration for storage
- Email/password + GitHub OAuth authentication

#### Memory System - Backend
1. **Admin Configuration** (JWT Protected)
   - Entity types/subtypes management
   - Lesson types with colors
   - Channel types
   - Agent credentials with API keys
   - LLM API configs per task (summarization, embedding, vision, NER, PII)
   - System prompts for LLM operations
   - General settings

2. **Ingestion Pipeline** (Agent API Key Protected)
   - `POST /api/memory/interactions`
   - Document parsing (text + file attachments)
   - Text chunking (configurable)
   - Entity extraction (GLiNER2 or LLM fallback)
   - Summary generation
   - Embedding → Qdrant storage
   - PII scrubbing for shared memories
   - Rate limiting
   - Audit logging

3. **Retrieval APIs**
   - `POST /api/memory/search` - Semantic search
   - `GET /api/memory/timeline/{type}/{id}` - Entity timeline
   - `GET /api/memory/daily/{date}` - Daily log
   - `GET/POST/PUT/DELETE /api/memory/admin/lessons` - Lessons CRUD

4. **Background Tasks**
   - OpenClaw Markdown sync (export to filesystem)
   - Automated lesson mining
   - Rate limiting per agent
   - Agent activity monitoring/stats

#### Memory System - Frontend
1. **Memory Settings** (`/app/memory`)
   - LLM APIs tab - Configure API keys for each task
   - Entities tab - Manage entity types and subtypes
   - Lessons tab - Manage lesson types
   - Channels tab - Manage channel types
   - Agents tab - Create agents with API keys
   - General tab - Chunking, PII, rate limiting

2. **Memory Explorer** (`/app/memory/explore`)
   - Semantic Search with filters
   - Entity Timeline view
   - Daily Log browser
   - Lessons management (create, edit, approve, delete)

3. **System Monitor** (`/app/memory/monitor`)
   - Stats overview (memories, documents, lessons, agents)
   - OpenClaw sync trigger
   - Lesson mining trigger
   - Agent activity visualization

---

## API Endpoints

### Authentication
- All `/api/memory/config/*` endpoints require JWT (admin)
- All `/api/memory/interactions` requires X-API-Key (agent)
- All `/api/memory/admin/*` endpoints require JWT (admin)

### Memory System APIs
```
# Health
GET  /api/memory/health

# Config (JWT auth)
GET/POST/DELETE  /api/memory/config/entity-types
GET/POST/DELETE  /api/memory/config/entity-subtypes
GET/POST/DELETE  /api/memory/config/lesson-types
GET/POST/DELETE  /api/memory/config/channel-types
GET/POST/PATCH/DELETE  /api/memory/config/agents
GET/POST/PUT/DELETE  /api/memory/config/llm-configs
GET/POST/PUT/DELETE  /api/memory/config/system-prompts
GET/PUT  /api/memory/config/settings

# Agent APIs (API Key auth)
POST  /api/memory/interactions
GET   /api/memory/search
GET   /api/memory/timeline/{entity_type}/{entity_id}
GET   /api/memory/lessons

# Admin UI APIs (JWT auth)
GET   /api/memory/daily/{date}
GET   /api/memory/memories/{id}
POST  /api/memory/search
GET   /api/memory/admin/timeline/{entity_type}/{entity_id}
GET/POST/PUT/DELETE  /api/memory/admin/lessons
GET   /api/memory/admin/stats
GET   /api/memory/admin/stats/agents
POST  /api/memory/admin/sync/openclaw
POST  /api/memory/admin/tasks/mine-lessons
```

---

## Test Credentials
- **Admin Email**: admin@promptsrc.com
- **Admin Password**: admin123
- **Agent API Key**: mem_YhZtU7wjp8-gFQKAjyT7ZwKzTC3L7R7I6cqHM3oJbYA

---

## File Structure
```
/app/
├── backend/
│   ├── server.py             # Main FastAPI app
│   ├── memory_db.py          # Memory system DB
│   ├── memory_models.py      # Pydantic models
│   ├── memory_routes.py      # Memory API routes
│   ├── memory_services.py    # LLM/Vector services
│   └── memory_tasks.py       # Background tasks
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── MemorySettingsPage.jsx
│   │   │   ├── MemoryExplorerPage.jsx
│   │   │   └── MemoryMonitorPage.jsx
│   │   └── lib/api.js
├── gliner/
│   ├── Dockerfile
│   └── app.py
└── docker-compose.yml
```

---

## Tech Stack
- **Backend**: FastAPI, SQLite/PostgreSQL, Qdrant
- **Frontend**: React, Tailwind, Shadcn/UI
- **NER**: GLiNER2 (Docker service)
- **Auth**: JWT (admin), API Keys (agents)

---

## Future Enhancements
- Bulk import/export functionality
- GLiNER model customization
- Real-time activity dashboard
- Webhook notifications for new lessons
